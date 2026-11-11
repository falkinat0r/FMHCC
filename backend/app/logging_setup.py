"""Strukturiertes (JSON-Zeilen) Logging mit Request-Id-Kontext.

Produktiv wird nach /var/log/hcc geleitet; Format ist maschinenlesbar und
maskiert bekannte Secret-Felder (siehe docs/foundation-handoff.md).
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("hcc_request_id", default=None)

_MASKED_FIELDS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "client_secret",
        "private_key",
        "authorization",
        "cookie",
        "session_token",
        "csrf_token",
        "bootstrap_token",
    }
)


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z") or None,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonLineFormatter())
    root.handlers = [handler]
    # Dritte Bibliotheken nicht zu laut machen
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def mask_value(value: str) -> str:
    """Maskiert Stringwerte fuer Logs/Audit-Details."""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def mask_fields(data: dict[str, object]) -> dict[str, object]:
    """Recursiv bekannte Secret-Felder maskieren."""
    out: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[key] = mask_fields(value)
        elif key.lower() in _MASKED_FIELDS and isinstance(value, str):
            out[key] = mask_value(value)
        else:
            out[key] = value
    return out
