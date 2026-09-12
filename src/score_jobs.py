from pathlib import Path

from openai import OpenAI
from pyspark.sql import SparkSession

from config import CONFIG, project_path
from logger import get_logger
import json


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


def score_job(job_description, resume):
    response = client.responses.create(
        model="gpt-5.6-luna",

        input=f"""
You are helping a job seeker decide whether they should apply for a job.

CANDIDATE PROFILE:
{resume}

JOB DESCRIPTION:
{job_description}

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

def main():
    spark = create_spark_session()

    try:
        logger.info("Reading processed jobs")

        df = spark.read.parquet(str(OUTPUT_PATH))

        resume = load_resume()

        # ONLY ONE JOB FOR NOW
        job = df.first()

        print("\nJOB")
        print("=" * 60)
        print(job.job_title)
        print(job.company)
        print(job.location)

        print("\nSCORING...")
        print("=" * 60)

        result = score_job(
            job.description,
            resume,
        )

        print(result)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
