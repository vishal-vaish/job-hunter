"""
Application Logging Module.

This file is responsible for:
- Providing unified, structured logging across all system components.
- Directing log messages to both the standard console (stdout) and persistent logs in sandbox/logs/agent.log.
- Supporting phase-specific tags to track the Brain's feedback loop:
  [OBSERVE], [DIAGNOSE], [DECIDE], [ACT], [REFLECT].
- Ensuring safe file-handling within the designated sandbox boundary without external leakage.
"""

import logging
import sys
from pathlib import Path
from config.settings import settings
from security.sandbox import default_sandbox


_logger_initialized = False


def setup_logger(name: str = "job_hunter") -> logging.Logger:
    """
    Configures and returns the application logger.
    Attaches handlers to the root logger so all child loggers propagate and
    write formatted output to stdout and sandbox/logs/agent.log.
    """
    global _logger_initialized
    root_logger = logging.getLogger()

    if not _logger_initialized:
        # Set log level from settings
        level = getattr(logging, settings.log_level, logging.INFO)
        root_logger.setLevel(level)

        # Clear existing handlers to prevent duplicates
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        # Formatter for structured readability
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 1. Console Stream Handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 2. File Handler writing directly to sandbox/logs/agent.log
        try:
            log_file_path = default_sandbox.resolve_safe_path("logs", "agent.log")
            file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            console_handler.handle(
                logging.LogRecord(
                    name="logger",
                    level=logging.WARNING,
                    pathname=__file__,
                    lineno=50,
                    msg=f"Could not initialize file logging in sandbox: {e}",
                    args=(),
                    exc_info=None
                )
            )

        _logger_initialized = True

    return logging.getLogger(name)


def get_logger(name: str = "job_hunter") -> logging.Logger:
    """
    Retrieves a logger instance. Ensures root logging handlers are initialized.
    """
    if not _logger_initialized:
        setup_logger()
    return logging.getLogger(name)
