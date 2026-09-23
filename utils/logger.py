"""
Application Logging Module.

This file is responsible for:
- Providing unified, structured logging across all system components.
- Generating unique execution run IDs (run_YYYYMMDD_HHMMSS_<hex>).
- Directing per-run log messages to isolated files in sandbox/logs/<run_id>.log.
- Injecting the active run_id into every log record:
  [%(asctime)s] [%(run_id)s] [%(levelname)s] [%(name)s] %(message)s.
- Mirroring log records to stdout for real-time console streaming.
- Closing per-run handlers cleanly at the conclusion or failure of a run.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Any, Optional
import uuid

from config.settings import settings
from security.sandbox import default_sandbox


_logger_initialized = False
_active_run_id: str = "system"
_current_file_handler: Optional[logging.FileHandler] = None


def generate_run_id() -> str:
    """
    Generates a unique execution run ID in the preferred format:
    run_YYYYMMDD_HHMMSS_<short_unique_id>
    Example: run_20260923_143522_a81f
    """
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:4]
    return f"run_{now_str}_{short_id}"


class RunIdFilter(logging.Filter):
    """
    Injects the active run_id attribute into every LogRecord.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = getattr(record, "run_id", _active_run_id)
        return True


def setup_logger(
    name: str = "job_hunter",
    run_id: Optional[str] = None,
    sandbox: Optional[Any] = None
) -> logging.Logger:
    """
    Configures and returns the application logger.
    Attaches handlers to the root logger so all child loggers propagate and
    write formatted output to stdout and sandbox/logs/<run_id>.log.
    """
    global _logger_initialized, _active_run_id, _current_file_handler
    root_logger = logging.getLogger()

    if run_id:
        _active_run_id = run_id

    # Set log level from settings
    level = getattr(logging, settings.log_level, logging.INFO)
    root_logger.setLevel(level)

    # Formatter for structured readability with run_id
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(run_id)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    id_filter = RunIdFilter()

    if not _logger_initialized:
        # Clear existing handlers
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        # 1. Console Stream Handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(id_filter)
        root_logger.addHandler(console_handler)

        _logger_initialized = True

    # 2. Configure per-run File Handler if run_id is supplied
    if run_id:
        # Remove previous file handler if exists
        if _current_file_handler:
            if _current_file_handler in root_logger.handlers:
                root_logger.removeHandler(_current_file_handler)
            try:
                _current_file_handler.flush()
                _current_file_handler.close()
            except Exception:
                pass
            _current_file_handler = None

        try:
            log_filename = f"{run_id}.log"
            target_sandbox = sandbox or default_sandbox
            log_file_path = target_sandbox.resolve_safe_path("logs", log_filename)
            file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(id_filter)
            root_logger.addHandler(file_handler)
            _current_file_handler = file_handler
        except Exception as e:
            sys.stderr.write(f"Warning: Could not initialize run file logging in sandbox: {e}\n")

    return logging.getLogger(name)


def get_logger(name: str = "job_hunter") -> logging.Logger:
    """
    Retrieves a logger instance. Ensures root logging handlers are initialized.
    """
    if not _logger_initialized:
        setup_logger()
    return logging.getLogger(name)


def close_run_logger() -> None:
    """
    Flushes and closes the active per-run file handler cleanly.
    """
    global _current_file_handler
    root_logger = logging.getLogger()
    if _current_file_handler:
        if _current_file_handler in root_logger.handlers:
            root_logger.removeHandler(_current_file_handler)
        try:
            _current_file_handler.flush()
            _current_file_handler.close()
        except Exception:
            pass
        _current_file_handler = None
