import os
import psycopg 
from config import CONFIG 
from logger import get_logger 

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

    logger.info("Upserted %s jobs into PostgreSQL", len(jobs))

if __name__ == "__main__":
    create_tables()

