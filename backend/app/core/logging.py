"""Structured JSON logs with secret redaction and request ids."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

SECRET_KEYS = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie)", re.I)
SECRET_VALUES = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9_\-\.]{8,})")


def redact(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[depth]"
    if isinstance(value, dict):
        return {k: ("[redacted]" if SECRET_KEYS.search(str(k)) else redact(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v, depth + 1) for v in value]
    if isinstance(value, str):
        return SECRET_VALUES.sub("[redacted]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
            "request_id": request_id_var.get(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(redact(extra))
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel("WARNING")


def log_event(logger: logging.Logger, msg: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, msg, extra={"extra_fields": fields})
