"""SSE subscriber for /v1/stream. Events are hints only; handlers re-fetch REST state.

- Comment lines (": connected", ": keepalive") are ignored by the parser.
- 15 s of silence is normal (the server sends a keepalive); the read timeout is well above that.
- A 503 (stream_disconnect or unavailable fault) or any drop triggers a reconnect with exponential backoff and jitter.
- There is no replay, so every (re)connect triggers a full refresh.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from httpx_sse import aconnect_sse

from app.logs import event
from app.metrics import SSE_CONNECTED, SSE_EVENTS, SSE_RECONNECTS
from app.sim.errors import error_for

log = logging.getLogger("app.sse")

Handler = Callable[[str, Any], Awaitable[None]]
CONNECTED = "_connected"


class SSEListener:
    def __init__(
        self,
        base_url: str,
        handler: Handler,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        read_timeout: float = 45.0,
        backoff_initial: float = 1.0,
        backoff_max: float = 30.0,
    ):
        self.base_url = base_url
        self.handler = handler
        self.transport = transport
        self.read_timeout = read_timeout
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.connected = False
        self.reconnects = 0
        self.last_event_at: float | None = None
        self.last_error: str | None = None
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        delay = self.backoff_initial
        timeout = httpx.Timeout(5.0, read=self.read_timeout)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=self.transport) as http:
            while not self._stop.is_set():
                try:
                    await self.consume(http)
                    delay = self.backoff_initial  # clean end of stream: reconnect quickly
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    event(log, "sse_error", logging.WARNING, error=self.last_error, retry_in_s=round(delay, 2))
                finally:
                    if self.connected:
                        event(log, "sse_disconnected")
                    self._set_connected(False)
                if self._stop.is_set():
                    break
                SSE_RECONNECTS.inc()
                self.reconnects += 1
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay * (0.5 + random.random()))
                except TimeoutError:
                    pass
                delay = min(self.backoff_max, delay * 2)

    async def consume(self, http: httpx.AsyncClient) -> None:
        async with aconnect_sse(http, "GET", "/v1/stream") as source:
            resp = source.response
            if resp.status_code != 200:
                body = await resp.aread()
                raise error_for(resp.status_code, body)
            self._set_connected(True)
            event(log, "sse_connected")
            await self.handler(CONNECTED, None)
            async for sse in source.aiter_sse():
                if not sse.event and not sse.data:
                    continue
                name = sse.event or "message"
                SSE_EVENTS.labels(name).inc()
                self.last_event_at = time.time()
                try:
                    data = json.loads(sse.data) if sse.data else None
                except ValueError:
                    data = sse.data
                await self.handler(name, data)

    def _set_connected(self, value: bool) -> None:
        self.connected = value
        SSE_CONNECTED.set(1 if value else 0)
