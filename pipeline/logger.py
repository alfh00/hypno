import logging
import os
from pathlib import Path

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_DIR = Path("./logs")


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with console + file handlers (idempotent)."""
    _LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(_LOG_LEVEL)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(_LOG_DIR / "drift.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
