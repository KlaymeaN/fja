from e import run_linkedin_ingestion
from ingest_api import run_api_ingestion
from t import run_transform
from logger import get_logger


logger = get_logger(__name__)


def main():

    logger.info("Starting Job Market Data Pipeline")

    try:
        logger.info("Step 1/3: LinkedIn ingestion")
        run_linkedin_ingestion()

        logger.info("Step 2/3: API ingestion")
        run_api_ingestion()

        logger.info("Step 3/3: Spark transformation")
        run_transform()

        logger.info(
            "Job Market Data Pipeline completed successfully"
        )

    except Exception:
        logger.exception(
            "Job Market Data Pipeline failed"
        )

        raise


if __name__ == "__main__":
    main()
