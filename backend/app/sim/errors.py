"""Typed simulator errors and parsing of both error shapes.

Faults:      {"error": {"code": "FAULT_INJECTED", "message": "..."}}
Domain:      {"detail": {"code": "ROUTE_DISRUPTED", "message": "..."}}
Validation:  {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}
"""

from __future__ import annotations

import json
from typing import Any


class SimError(Exception):
    def __init__(self, status: int | None, code: str, message: str = ""):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class SimUnavailable(SimError):
    """503, timeout or connection error: transient, safe to retry GETs and replay POSTs with the same key."""


class SimConflict(SimError):
    """409 domain rule violation. Never blindly retried."""


class SimNotFound(SimError):
    """404 NOT_FOUND / ALLOCATION_NOT_FOUND."""


class SimValidation(SimError):
    """422 request validation failure."""


class CircuitOpen(SimError):
    def __init__(self) -> None:
        super().__init__(None, "CIRCUIT_OPEN", "Simulator circuit breaker is open")


def parse_error_body(body: Any, status: int | None = None) -> tuple[str, str]:
    """Return (code, message) from any of the simulator's error shapes."""
    if isinstance(body, (bytes, str)):
        try:
            body = json.loads(body)
        except (ValueError, TypeError):
            text = body.decode(errors="replace") if isinstance(body, bytes) else body
            return (f"HTTP_{status}" if status else "UNKNOWN"), text[:200]
    if isinstance(body, dict):
        for key in ("error", "detail"):
            inner = body.get(key)
            if isinstance(inner, dict):
                return str(inner.get("code") or f"HTTP_{status}"), str(inner.get("message") or "")
            if isinstance(inner, list):
                msgs = []
                for item in inner:
                    if isinstance(item, dict):
                        loc = ".".join(str(x) for x in item.get("loc", []) if x != "body")
                        msgs.append(f"{loc}: {item.get('msg', '')}".strip(": "))
                return "VALIDATION_ERROR", "; ".join(msgs)
            if isinstance(inner, str):
                return f"HTTP_{status}" if status else "UNKNOWN", inner
    return (f"HTTP_{status}" if status else "UNKNOWN"), ""


def error_for(status: int, body: Any) -> SimError:
    code, message = parse_error_body(body, status)
    if status == 409:
        return SimConflict(status, code, message)
    if status == 404:
        return SimNotFound(status, code, message)
    if status == 422:
        return SimValidation(status, code, message)
    if status in (502, 503, 504) or status >= 500:
        return SimUnavailable(status, code, message)
    return SimError(status, code, message)
