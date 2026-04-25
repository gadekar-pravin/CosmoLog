"""Centralized logging configuration with async-safe correlation IDs."""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="no-request")


def get_correlation_id() -> str:
    return correlation_id.get()


def set_correlation_id(value: str) -> None:
    correlation_id.set(value)


class CorrelationFilter(logging.Filter):
    """Inject the current correlation_id into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get()  # type: ignore[attr-defined]
        return True


def _truncate(value: object, max_len: int = 500) -> str:
    """Safely stringify and length-cap a value for log output."""
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


_configured = False


def configure_logging() -> None:
    """Set up root logger with correlation filter. Idempotent."""
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "%(asctime)s %(levelname)-8s [%(correlation_id)s] %(name)s: %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(CorrelationFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for name in ("httpx", "httpcore", "google", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
