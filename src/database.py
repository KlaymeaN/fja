import os
import psycopg 
from psycopg.rows import dict_row
from config import CONFIG 
from logger import get_logger 


#from database import get_pending_ai_jobs

logger = get_logger(__name__)

DB_CONFIG= CONFIG["database"]

def get_connection():
    password = os.environ.get("JOB_DB_PASSWORD")

    if not password:
        raise RuntimeError(
            "JOB_DB_PASSWORD environment variable is not set"
        )

    return psycopg.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        dbname=DB_CONFIG["name"],
        user=DB_CONFIG["user"],
        password=password,
    )


def create_tables():
    query="""
    CREATE TABLE IF NOT EXISTS jobs (
        id BIGSERIAL PRIMARY KEY, 

        source VARCHAR(50) NOT NULL,
        source_job_id VARCHAR(255) NOT NULL,

        job_title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT,
        country VARCHAR(100),
        date_posted DATE,

        job_url TEXT,
        application_type VARCHAR(50),
        description TEXT,

        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        ai_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        ai_score INTEGER,
        ai_decision VARCHAR(20),
        ai_reason TEXT,
        ai_attempts INTEGER NOT NULL DEFAULT 0,
        ai_error TEXT,
        scored_at TIMESTAMPTZ,

        telegram_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        telegram_sent_at TIMESTAMPTZ,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        UNIQUE (source, source_job_id)
        );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()
    logger.info("Database tables initialized")



def upsert_jobs(jobs):
    if not jobs:
        return {
            "received": 0,
            "new": 0,
            "existing": 0,
        }

    before_count = get_total_job_count()

    query = """
        INSERT INTO jobs (
            source,
            source_job_id,
            job_title,
            company,
            location,
            country,
            date_posted,
            job_url,
            application_type,
            description
        )
        VALUES (
            %(source)s,
            %(source_job_id)s,
            %(job_title)s,
            %(company)s,
            %(location)s,
            %(country)s,
            %(date_posted)s,
            %(job_url)s,
            %(application_type)s,
            %(description)s
        )
        ON CONFLICT (source, source_job_id)
        DO UPDATE SET
            job_title = EXCLUDED.job_title,
            company = EXCLUDED.company,
            location = EXCLUDED.location,
            country = EXCLUDED.country,
            date_posted = EXCLUDED.date_posted,
            job_url = EXCLUDED.job_url,
            application_type = EXCLUDED.application_type,
            description = EXCLUDED.description,
            last_seen_at = NOW(),
            updated_at = NOW();
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, jobs)

        conn.commit()

    after_count = get_total_job_count()

    new_jobs = after_count - before_count
    existing_jobs = len(jobs) - new_jobs

    logger.info(
        "Database upsert complete: %s received, %s new, %s existing",
        len(jobs),
        new_jobs,
        existing_jobs,
    )

    return {
        "received": len(jobs),
        "new": new_jobs,
        "existing": existing_jobs,
    }


def get_pending_ai_jobs(limit=100):
    query = """
        SELECT
            id,
            job_title,
            company,
            location,
            country,
            date_posted,
            job_url,
            application_type,
            description
        FROM jobs
        WHERE ai_status = 'pending'
            AND ai_attempts < 3
        ORDER BY first_seen_at ASC
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

    return rows


#jobs = get_pending_ai_jobs()
#print("Pending Jobs:", len(jobs))

#print(jobs[0])
#print(jobs[0]["job_title"])
#print(jobs[0]["company"])

def update_job_ai_result(job_id, result):
    query = """
        UPDATE jobs
        SET
            ai_status = 'completed',
            ai_score = %s,
            ai_decision = %s,
            ai_reason = %s,
            ai_error = NULL,
            scored_at = NOW(),
            updated_at = NOW()
        WHERE id = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    result["match_score"],
                    result["recommendation"],
                    result["reason"],
                    job_id,
                ),
            )

        conn.commit()

    logger.info("Saved AI result for job id %s", job_id)


def mark_job_ai_failure(job_id, error_message, max_attempts=3):
    query = """
        UPDATE jobs
        SET
            ai_attempts = ai_attempts + 1,
            ai_error = %s,
            ai_status = CASE
                WHEN ai_attempts + 1 >= %s THEN 'failed'
                ELSE 'pending'
            END,
            updated_at = NOW()
        WHERE id = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    error_message,
                    max_attempts,
                    job_id,
                ),
            )

        conn.commit()

    logger.warning(
        "AI scoring failed for job id %s",
        job_id,
    )


def get_pending_telegram_jobs(decision="APPLY", limit=20):
    query = """
        SELECT
            id,
            job_title,
            company,
            location,
            country,
            date_posted,
            job_url,
            ai_score,
            ai_decision,
            ai_reason
        FROM jobs
        WHERE ai_status = 'completed'
          AND ai_decision = %s
          AND telegram_status = 'pending'
        ORDER BY ai_score DESC, date_posted DESC
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                query,
                (decision, limit),
            )
            rows = cur.fetchall()

    return rows

def mark_job_telegram_sent(job_id):
    query = """
        UPDATE jobs
        SET
            telegram_status = 'sent',
            telegram_sent_at = NOW(),
            updated_at = NOW()
        WHERE id = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (job_id,),
            )

        conn.commit()

    logger.info(
        "Marked job %s as sent to Telegram",
        job_id,
    )


def get_job_counts_by_decision():
    query = """
        SELECT
            ai_decision,
            COUNT(*) AS total_count,
            COUNT(*) FILTER (
                WHERE telegram_status = 'pending'
            ) AS pending_count
        FROM jobs
        WHERE ai_status = 'completed'
        GROUP BY ai_decision;
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query)
            rows = cur.fetchall()

    counts = {
        "APPLY": {
            "total": 0,
            "pending": 0,
        },
        "MAYBE": {
            "total": 0,
            "pending": 0,
        },
        "SKIP": {
            "total": 0,
            "pending": 0,
        },
    }

    for row in rows:
        decision = row["ai_decision"]

        if decision in counts:
            counts[decision]["total"] = row["total_count"]
            counts[decision]["pending"] = row["pending_count"]

    return counts

def get_total_job_count():
    query = """
        SELECT COUNT(*) AS total
        FROM jobs;
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query)
            row = cur.fetchone()

    return row["total"]

if __name__ == "__main__":
    create_tables()

#    jobs = get_pending_telegram_jobs("APPLY")
#
#    print(f"Found {len(jobs)} APPLY jobs")
#
#    for job in jobs:
#        print(
#            job["id"],
#            job["ai_score"],
#            job["job_title"],
#            job["company"],
#        )

