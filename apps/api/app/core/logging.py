"""Structured JSON logging with a per-request id (docs/12).

A single stdout handler emits one JSON object per line, each stamped with the current
request id from :data:`request_id_ctx` (set by the request middleware in ``main.py``).
Never log secrets or tokens — log hash prefixes if identity is needed.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

# Bound per request by the HTTP middleware; "-" outside a request scope.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes present on every LogRecord — anything else is treated as structured extra.
_RESERVED = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a compact JSON line, including any ``extra=`` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger (idempotent)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def new_request_id() -> str:
    """A fresh short request id (no dashes)."""
    return uuid.uuid4().hex


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
