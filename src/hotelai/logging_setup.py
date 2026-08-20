"""Centralized logging: one timestamped FileHandler, configured once per entrypoint.

Every `logger = logging.getLogger(__name__)` already used across the codebase
(structured_extractor, rag_engine, api.main, ...) writes through whatever this configures,
since Python loggers propagate to the root logger by default. Call `configure_logging()`
once, early, in each real entrypoint (`api/main.py`, `mcp_server/server.py`, CLI scripts'
`__main__` blocks) — it also installs a `sys.excepthook` so any `raise` that is never
caught (FileNotFoundError, ValueError, RuntimeError, ...) still lands in the log file with
a timestamp before the process exits, not just whatever scrolled off the terminal.

This does not change what gets raised or caught anywhere — it only makes sure raises are
recorded somewhere durable. Routine, expected errors (e.g. FastAPI's own 422 validation
responses) are deliberately not logged here; only genuine failures are.
"""
from __future__ import annotations

import logging
import sys
from types import TracebackType

from .config import settings

_configured = False


def configure_logging() -> None:
    """Idempotent: safe to call from multiple entrypoints (e.g. a test importing api.main)."""
    global _configured
    if _configured:
        return
    _configured = True

    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(settings.log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)

    sys.excepthook = _log_uncaught_exception


def _log_uncaught_exception(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: TracebackType | None
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.getLogger("uncaught").critical("Eccezione non gestita", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
