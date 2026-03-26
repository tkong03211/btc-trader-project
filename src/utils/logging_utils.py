from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Include structured fields if the user passed extras={...}
        extras = getattr(record, "extras", None)
        if isinstance(extras, dict):
            payload.update(extras)

        # If exception info exists, include it.
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, sort_keys=True)


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure root logging.

    If LOG_JSON=1, log records are emitted as single-line JSON suitable for ingestion.
    """

    log_json = os.getenv("LOG_JSON", "").strip().lower() in {"1", "true", "yes", "y"}
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if log_json:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)sZ %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_kv(logger: logging.Logger, level: int, msg: str, **fields: Any) -> None:
    """
    Convenience for structured logging without depending on extra libraries.
    """

    logger.log(level, msg, extra={"extras": fields})

