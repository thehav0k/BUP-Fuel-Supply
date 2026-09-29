"""Calls the prediction service (1 s timeout); falls back to the uncalibrated baseline in-process."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

import fuelcore
from app.logs import event
from app.metrics import FALLBACK_ACTIVE, PREDICTION_REQUESTS
from app.state import Snapshot

log = logging.getLogger("app.forecaster")
DEMAND_WINDOW_TICKS = 32


class Forecaster:
    def __init__(
        self, base_url: str, *, timeout: float = 1.0, horizon: int = 48, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self.horizon = horizon
        self.fallback = False
        self.last_ok_at: float | None = None
        self.last_error: str | None = None
        self.last_latency_ms: float | None = None

    async def close(self) -> None:
        await self.http.aclose()

    def build_request(self, snap: Snapshot, demand: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "tick": snap.tick,
            "sim_time": snap.sim_time,
            "tick_minutes": snap.tick_minutes,
            "horizon": self.horizon,
            "regions": snap.regions,
            "stations": snap.stations,
            "depots": snap.depots,
            "routes": snap.routes,
            "events": snap.events,
            "allocations": snap.in_flight(),
            "supply_arrivals": [s for s in snap.supply_arrivals if s.get("status") != "ARRIVED"],
            "demand": demand,
        }

    async def analyze(self, snap: Snapshot, demand: list[dict[str, Any]]) -> dict[str, Any]:
        request = self.build_request(snap, demand)
        started = time.perf_counter()
        try:
            resp = await self.http.post("/risk", json=request)
            resp.raise_for_status()
            result = resp.json()
            self.last_latency_ms = round((time.perf_counter() - started) * 1000, 1)
            self.last_ok_at = time.time()
            self.last_error = None
            PREDICTION_REQUESTS.labels("ok").inc()
            self._set_fallback(False)
        except (httpx.HTTPError, ValueError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            PREDICTION_REQUESTS.labels("error").inc()
            self._set_fallback(True)
            result = fuelcore.analyze(request, calibrate_enabled=False)
        result["fallback"] = self.fallback
        return result

    def _set_fallback(self, value: bool) -> None:
        if value != self.fallback:
            event(log, "fallback_on" if value else "fallback_off", logging.WARNING if value else logging.INFO,
                  error=self.last_error)
        self.fallback = value
        FALLBACK_ACTIVE.set(1 if value else 0)

    async def healthy(self) -> bool:
        try:
            resp = await self.http.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
