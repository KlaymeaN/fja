import logging
from config import CONFIG, project_path


#PROJECT_ROOT = Path(__file__).resolve().parent.parent
#
#LOG_DIR = PROJECT_ROOT / "logs"
#LOG_DIR.mkdir(parents=True, exist_ok=True)
#
#LOG_FILE = LOG_DIR / "pipeline.log"
LOGGING_CONFIG = CONFIG["logging"]

LOG_DIR = project_path(
    LOGGING_CONFIG["directory"]
)

LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / LOGGING_CONFIG["filename"]


def get_logger(name):
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    #logger.setLevel(logging.INFO)
    log_level = getattr(
    logging,
    LOGGING_CONFIG["level"].upper()
)

    logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
