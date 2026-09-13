from pathlib import Path

from openai import OpenAI
#from pyspark.sql import SparkSession

from config import CONFIG, project_path
from logger import get_logger
import json

from database import get_pending_ai_jobs, update_job_ai_result, mark_job_ai_failure


logger = get_logger(__name__)

client = OpenAI()

OUTPUT_PATH = project_path(
    CONFIG["paths"]["processed_jobs"]
)

RESUME_PATH = project_path(
    "config/resume.txt"
)


def create_spark_session():
    return (
        SparkSession.builder
        .appName("JobScoring")
        .master("local[*]")
        .getOrCreate()
    )


def load_resume():
    return RESUME_PATH.read_text(encoding="utf-8")


def score_job(job, resume):
    response = client.responses.create(
        model="gpt-5.6-luna",

        input=f"""
You are helping a job seeker decide whether they should apply for a job.

CANDIDATE PROFILE:
{resume}

JOB TITLE:
{job["job_title"]}

COMPANY:
{job["company"]}

LOCATION:
{job["location"]}

JOB DESCRIPTION:
{job["description"]}

Evaluate the candidate realistically. Do not give Extra information. 

Rules:
- Do not assume skills or experience that are not in the candidate profile.
- Consider required experience, technical skills, education, languages,
  seniority, and domain knowledge.
- A score above 75 should indicate a genuinely strong application opportunity.
- Be stricter about mandatory requirements than preferred requirements.
- Return at most 2 short strengths.
- Return at most 2 short gaps.
- Each strength/gap should be only a few words.
- The reason must be exactly one short sentence.
- If the job asks that you need to have valid work permit or EU citizenship it is an instant SKIP
""",

        text={
            "format": {
                "type": "json_schema",
                "name": "job_match",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "match_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100
                        },
                        "recommendation": {
                            "type": "string",
                            "enum": ["APPLY", "MAYBE", "SKIP"]
                        },
                        "strengths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 2
                        },
                        "gaps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems":2
                        },
                        "reason": {
                            "type": "string",
                            "description": "Exactly one short sentence explainig the overall match"
                        }
                    },
                    "required": [
                        "match_score",
                        "recommendation",
                        "strengths",
                        "gaps",
                        "reason"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(response.output_text)

def run_ai_scoring():
    resume = load_resume()

    stats = {
        "pending_found": 0,
        "scored": 0,
        "apply": 0,
        "maybe": 0,
        "skip": 0,
        "failed": 0,
    }

    while True:
        jobs = get_pending_ai_jobs(limit=500)

        if not jobs:
            logger.info("No more pending jobs to score")
            break

        stats["pending_found"] += len(jobs)

        logger.info(
            "Found %s pending jobs in this batch",
            len(jobs),
        )

        for job in jobs:
            try:
                logger.info(
                    "Scoring job %s: %s at %s",
                    job["id"],
                    job["job_title"],
                    job["company"],
                )

                result = score_job(job, resume)

                update_job_ai_result(
                    job["id"],
                    result,
                )

                stats["scored"] += 1

                decision = result["recommendation"]

                if decision == "APPLY":
                    stats["apply"] += 1

                elif decision == "MAYBE":
                    stats["maybe"] += 1

                elif decision == "SKIP":
                    stats["skip"] += 1

                logger.info(
                    "Job %s scored: %s (%s)",
                    job["id"],
                    decision,
                    result["match_score"],
                )

            except Exception as e:
                stats["failed"] += 1

                logger.exception(
                    "Failed to score job %s",
                    job["id"],
                )

                mark_job_ai_failure(
                    job["id"],
                    str(e),
                )

    return stats

#job = jobs[0]
#def main():
#    spark = create_spark_session()
#
#    try:
#        logger.info("Reading processed jobs")
#
#        df = spark.read.parquet(str(OUTPUT_PATH))
#
#        resume = load_resume()
#
#        # ONLY ONE JOB FOR NOW
#        job = df.first()
#
#        print("\nJOB")
#        print("=" * 60)
#        print(job.job_title)
#        print(job.company)
#        print(job.location)
#
#        print("\nSCORING...")
#        print("=" * 60)
#
#        result = score_job(
#            job.description,
#            resume,
#        )
#
#        print(result)
#
#    finally:
#        spark.stop()


if __name__ == "__main__":
    run_ai_scoring()
