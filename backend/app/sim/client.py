"""Async simulator client: timeouts, retry with backoff and jitter, circuit breaker, stale-header detection.

Only this module talks HTTP to the simulator.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.logs import event
from app.metrics import SIM_LATENCY, SIM_REQUESTS, SIM_STALE
from app.sim.breaker import CircuitBreaker
from app.sim.errors import CircuitOpen, SimError, SimUnavailable, error_for

log = logging.getLogger("app.sim")
_ID = re.compile(r"/\d+(?=/|$)")


@dataclass(frozen=True)
class SimResponse:
    data: Any
    stale: bool
    status: int


def endpoint_label(path: str) -> str:
    return _ID.sub("/{id}", path.split("?")[0])


class SimulatorClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.0,
        get_attempts: int = 3,
        breaker: CircuitBreaker | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        backoff_initial: float = 0.2,
        backoff_max: float = 1.0,
    ):
        self.base_url = base_url
        self.http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self.admin_http = httpx.AsyncClient(base_url=base_url, timeout=max(timeout, 10.0), transport=transport)
        self.breaker = breaker or CircuitBreaker()
        self.get_attempts = get_attempts
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.stale = False
        self.last_ok_at: float | None = None
        self.last_error: str | None = None

    async def close(self) -> None:
        await self.http.aclose()
        await self.admin_http.aclose()

    # ------------------------------------------------------------------ core

    async def _once(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        label = endpoint_label(path)
        if not self.breaker.allow():
            SIM_REQUESTS.labels(label, "circuit_open").inc()
            raise CircuitOpen()
        started = time.perf_counter()
        try:
            resp = await self.http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            self._failed(label, "timeout", f"timeout after {self.http.timeout.read}s")
            raise SimUnavailable(None, "TIMEOUT", str(exc) or "request timed out") from exc
        except httpx.TransportError as exc:
            self._failed(label, "connection_error", str(exc))
            raise SimUnavailable(None, "CONNECTION_ERROR", str(exc) or type(exc).__name__) from exc
        finally:
            SIM_LATENCY.labels(label).observe(time.perf_counter() - started)

        if resp.status_code >= 500:
            err = error_for(resp.status_code, resp.content)
            self._failed(label, "fault" if err.code == "FAULT_INJECTED" else "server_error", f"{err.code} {err.message}")
            raise err
        # Any non-5xx answer proves the simulator is up.
        self.breaker.success()
        self.last_ok_at = time.time()
        self.last_error = None
        if resp.status_code >= 400:
            err = error_for(resp.status_code, resp.content)
            SIM_REQUESTS.labels(label, f"http_{resp.status_code}").inc()
            raise err
        SIM_REQUESTS.labels(label, "ok").inc()
        return resp

    def _failed(self, label: str, result: str, detail: str) -> None:
        SIM_REQUESTS.labels(label, result).inc()
        self.breaker.failure()
        self.last_error = detail

    def _retrying(self, attempts: int) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential_jitter(initial=self.backoff_initial, max=self.backoff_max),
            retry=retry_if_exception_type(SimUnavailable),
            reraise=True,
        )

    # ------------------------------------------------------------------ reads

    async def get(self, path: str, params: dict[str, Any] | None = None) -> SimResponse:
        async for attempt in self._retrying(self.get_attempts):
            with attempt:
                resp = await self._once("GET", path, params=params)
        stale = resp.headers.get("x-simulator-stale", "").lower() == "true"
        return SimResponse(data=resp.json(), stale=stale, status=resp.status_code)

    def note_stale(self, stale: bool) -> None:
        if stale != self.stale:
            event(log, "stale_changed", stale=stale)
        self.stale = stale
        SIM_STALE.set(1 if stale else 0)

    async def health(self) -> dict[str, Any] | None:
        """GET /v1/health bypasses faults; used as a liveness probe, outside the breaker."""
        try:
            resp = await self.admin_http.get("/v1/health", timeout=2.0)
            return resp.json() if resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    # ------------------------------------------------------------------ writes

    async def create_allocation(self, body: dict[str, Any], attempts: int = 3) -> SimResponse:
        """POST /v1/allocations. 503 and timeouts are replayed with the same body and idempotency key.

        A replay of an already-created allocation returns 200 or 201; both are success.
        """
        async for attempt in self._retrying(attempts):
            with attempt:
                resp = await self._once("POST", "/v1/allocations", json=body)
        return SimResponse(data=resp.json(), stale=False, status=resp.status_code)

    async def cancel_allocation(self, allocation_id: int) -> SimResponse:
        resp = await self._once("POST", f"/v1/allocations/{allocation_id}/cancel")
        return SimResponse(data=resp.json(), stale=False, status=resp.status_code)

    # ------------------------------------------------------------------ admin (tests and demo only)

    async def admin(self, method: str, path: str, json: Any = None) -> Any:
        label = endpoint_label(path)
        try:
            resp = await self.admin_http.request(method, path, json=json)
        except httpx.HTTPError as exc:
            SIM_REQUESTS.labels(label, "connection_error").inc()
            raise SimUnavailable(None, "CONNECTION_ERROR", str(exc) or type(exc).__name__) from exc
        SIM_REQUESTS.labels(label, "ok" if resp.status_code < 400 else f"http_{resp.status_code}").inc()
        if resp.status_code >= 400:
            raise error_for(resp.status_code, resp.content)
        return resp.json()


__all__ = ["CircuitOpen", "SimError", "SimResponse", "SimUnavailable", "SimulatorClient"]
