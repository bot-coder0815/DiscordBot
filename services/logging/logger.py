import logging
import sys
from pathlib import Path


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(name: str = "bot") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

    file_handler = logging.FileHandler(
        LOG_DIR / f"{name}.log", encoding="utf-8", mode="a"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
