"""
Simple, centralized logging setup.

Why this file exists:
Instead of every module configuring its own logging (or using print()
everywhere, which you can't filter or save), each module calls
get_logger(__name__) here to get a properly configured logger. Messages
go to both the console and a log file, so you can review what happened
after a batch finishes running - which company was being processed,
which stage failed, how long things took.
"""

import logging

from config import settings

LOG_DIR = settings.PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "app.log"

# Tracks whether we've already set up logging this run, so calling
# get_logger() many times (once per module) doesn't add duplicate
# handlers and print every message multiple times.
_configured = False


def _configure_root_logger() -> None:
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),  # prints to the console
            logging.FileHandler(LOG_FILE, encoding="utf-8"),  # also saves to a file
        ],
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for one module. Call this once near the top of each
    module as: logger = get_logger(__name__)
    """
    _configure_root_logger()
    return logging.getLogger(name)
