from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "Backend/logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "strategy.log")


def get_strategy_logger() -> logging.Logger:

    logger = logging.getLogger("quantgrid.strategy")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=20 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logger.propagate = False

    return logger
