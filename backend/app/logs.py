"""JSON-lines logging with tick, component and event fields."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

current_tick: ContextVar[int | None] = ContextVar("current_tick", default=None)
_TICK: dict[str, int | None] = {"value": None}


def set_tick(tick: int | None) -> None:
    _TICK["value"] = tick


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "component": record.name.removeprefix("app."),
            "event": record.getMessage(),
            "tick": _TICK["value"],
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def event(logger: logging.Logger, name: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, name, extra={"fields": fields})
