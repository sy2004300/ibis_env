from __future__ import annotations

import logging
from pathlib import Path


LOGGER_NAME = "ibis_automation"


def configure_file_logging(workspace: Path) -> Path:
    log_directory = workspace / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "ibis_automation.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue
        if Path(handler.baseFilename).resolve() == log_path.resolve():
            return log_path
        logger.removeHandler(handler)
        handler.close()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return log_path


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def close_file_logging(log_path: Path) -> None:
    active_logger = logging.getLogger(LOGGER_NAME)
    for handler in list(active_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            active_logger.removeHandler(handler)
            handler.close()
