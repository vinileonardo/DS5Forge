"""Structured, low-dependency logging for core and platform workers."""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import deque
from typing import Any

_RECENT_LOGS: deque[dict[str, Any]] = deque(maxlen=200)
_BEARER_SECRET = re.compile(r"(?i)\bbearer\s+\S+")
_LABELED_SECRET = re.compile(
    r"(?i)(?P<label>\b(?:token|cookie|password|passwd|secret|authorization|api[_ -]?key)\b\s*[:=]\s*)\S+"
)


def _redact_log_text(value: str) -> str:
    value = _BEARER_SECRET.sub("Bearer [REDACTED]", value)
    return _LABELED_SECRET.sub(r"\g<label>[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_log_text(record.getMessage()),
        }
        for key in ("event", "error_code", "path", "device", "state", "thread"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = _redact_log_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class RecentLogHandler(logging.Handler):
    """Keep a small structured tail for bounded support diagnostics."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            value = json.loads(self.format(record))
            if isinstance(value, dict):
                _RECENT_LOGS.append(value)
        except (TypeError, ValueError):
            # A logging formatter must never take down the controller loop.
            return


def configure_logging(*, level: int = logging.INFO, stream: Any = None) -> None:
    recent = RecentLogHandler()
    console = logging.StreamHandler(stream or sys.stderr)
    console.setFormatter(JsonFormatter())
    root = logging.getLogger("ds5forge")
    root.handlers.clear()
    root.addHandler(recent)
    root.addHandler(console)
    root.setLevel(level)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    if not name.startswith("ds5forge"):
        name = f"ds5forge.{name}"
    return logging.getLogger(name)


def recent_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Return at most the newest bounded log records for support export."""

    return list(_RECENT_LOGS)[-max(0, min(limit, _RECENT_LOGS.maxlen or limit)) :]
