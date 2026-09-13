import time

from logger import get_logger
from e import run_linkedin_ingestion
from t import run_transform
from score_jobs import run_ai_scoring
from telegram_bot import send_message

logger = get_logger(__name__)


def run_pipeline():
    logger.info("=" * 50)
    logger.info("JOB PIPELINE STARTED")
    logger.info("=" * 50)

    try:
        send_message("🚀 Job pipeline started")
    except Exception:
        logger.exception(
            "Pipeline started, but start notification failed"
        )

    start_time = time.time()

    try:
        # STEP 1: INGESTION
        ingestion_stats = run_linkedin_ingestion()

        # STEP 2: TRANSFORMATION + DATABASE
        transform_stats = run_transform()

        # AI scoring
        ai_stats = run_ai_scoring()

        

        summary_message = (
            "✅ Pipeline complete\n\n"
            f"🆕 New jobs: {transform_stats['database']['new']}\n"
            f"✅ APPLY: {ai_stats['apply']}\n"
            f"🤔 MAYBE: {ai_stats['maybe']}\n"
            f"⛔ SKIP: {ai_stats['skip']}\n"
            f"❌ AI failures: {ai_stats['failed']}"
        )

        #send_message(summary_message)
        try:
            send_message(summary_message)
            logger.info("Pipeline summary sent to Telegram")
        
        except Exception:
            logger.exception(
                "Pipeline succeeded, but Telegram summary failed"
            )

        duration = time.time() - start_time

        logger.info("=" * 50)
        logger.info("PIPELINE RUN COMPLETE")
        logger.info("=" * 50)

        logger.info(
            "LinkedIn jobs fetched: %s",
            ingestion_stats["jobs_fetched"],
        )

        logger.info(
            "Jobs before filtering: %s",
            transform_stats["input_jobs"],
        )

        logger.info(
            "Jobs filtered out: %s",
            transform_stats["filtered_out"],
        )

        logger.info(
            "Jobs processed: %s",
            transform_stats["final_jobs"],
        )

        logger.info(
            "New jobs added: %s",
            transform_stats["database"]["new"],
        )

        logger.info(
            "Existing jobs updated: %s",
            transform_stats["database"]["existing"],
        )
        logger.info(
            "AI jobs scored: %s",
            ai_stats["scored"],
        )
        
        logger.info(
            "AI results: %s APPLY | %s MAYBE | %s SKIP",
            ai_stats["apply"],
            ai_stats["maybe"],
            ai_stats["skip"],
        )
        
        logger.info(
            "AI scoring failures: %s",
            ai_stats["failed"],
        )

        logger.info(
            "Pipeline duration: %.2f seconds",
            duration,
        )

        logger.info("Pipeline status: SUCCESS")
        logger.info("=" * 50)

        return {
            "status": "success",
            "duration_seconds": duration,
            "ingestion": ingestion_stats,
            "transform": transform_stats,
            "ai" : ai_stats,
        }

    except Exception as e:
        duration = time.time() - start_time

        logger.exception(
            "Pipeline FAILED after %.2f seconds",
            duration,
        )
        try:
            send_message(
                f"❌ Pipeline FAILED\n\n"
                f"After: {duration:.1f} seconds\n"
                f"Error: {str(e)[:500]}"
            )
        except Exception:
            logger.exception("Could not send failure notification")
    
        raise


if __name__ == "__main__":
    run_pipeline()
