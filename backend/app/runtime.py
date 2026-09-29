"""Wires the simulator client, SSE listener, sync loop, forecaster, planner, recommendations and persistence.

Sync (PRD 5.1): every poll interval (2 s) or when SSE says something changed, fetch the full state concurrently.
Only a complete, successful fetch replaces the last good state. A new tick triggers one decision cycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

import httpx

from app import engine
from app.config import Settings
from app.forecaster import DEMAND_WINDOW_TICKS, Forecaster
from app.logs import event, set_tick
from app.metrics import (
    ALLOCATION_FAILURES,
    CYCLE_SECONDS,
    DATA_AGE,
    DEGRADED,
    SERVICE_LEVEL,
    SIM_TICK,
    STATION_RISK,
    UNMET_LITERS,
)
from app.persistence import Persistence
from app.recommendations import RecommendationService
from app.sim.breaker import CircuitBreaker
from app.sim.client import SimulatorClient
from app.sim.errors import SimError
from app.sim.sse import CONNECTED, SSEListener
from app.state import Snapshot, StateStore

log = logging.getLogger("app.sync")

CORE = {
    "instance": "/v1/instance",
    "depots": "/v1/depots",
    "stations": "/v1/stations",
    "routes": "/v1/routes",
    "supply_arrivals": "/v1/supply-arrivals",
    "events": "/v1/events",
    "allocations": "/v1/allocations",
    "metrics": "/v1/metrics",
}
PARTIAL = {"allocations": "/v1/allocations", "depots": "/v1/depots"}


class Runtime:
    def __init__(
        self,
        settings: Settings,
        *,
        sim_transport: httpx.AsyncBaseTransport | None = None,
        prediction_transport: httpx.AsyncBaseTransport | None = None,
        explainer: Any = None,
    ):
        self.settings = settings
        self.started_at = time.time()
        self.state = StateStore()
        self.sim = SimulatorClient(
            settings.simulator_url,
            timeout=settings.sim_timeout_s,
            get_attempts=settings.sim_get_attempts,
            breaker=CircuitBreaker(settings.breaker_failures, settings.breaker_reset_s),
            transport=sim_transport,
        )
        self.forecaster = Forecaster(
            settings.prediction_url, timeout=settings.prediction_timeout_s, horizon=settings.horizon_ticks,
            transport=prediction_transport,
        )
        self.db = Persistence(settings.database_url)
        self.recs = RecommendationService(settings, self.sim, self.state, self.db, explainer=explainer)
        self.sse = SSEListener(settings.simulator_url, self.on_sse, transport=sim_transport)
        self.plan: engine.Plan | None = None
        self.sim_health: dict[str, Any] | None = None
        self.prediction_up: bool | None = None
        self.last_cycle_tick: int | None = None
        self.last_cycle_at: float | None = None
        self.last_cycle_ms: float | None = None
        self.cycle_error: str | None = None
        self._wake = asyncio.Event()
        self._pending: set[str] = set()
        self._reset_hint = False
        self._last_reset_at = 0.0
        self._last_full_at = 0.0
        self._refresh_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[Any]] = []
        self._stopping = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self.db.enabled:
            if await self.db.connect(attempts=3):
                self.recs.restore(await self.db.load_recent())
            self.db.start()
        if self.settings.enable_sync:
            self._tasks.append(asyncio.create_task(self.sync_loop(), name="sync-loop"))
            self._tasks.append(asyncio.create_task(self.health_loop(), name="health-loop"))
        if self.settings.enable_sse:
            self._tasks.append(asyncio.create_task(self.sse.run(), name="sse"))

    async def stop(self) -> None:
        self._stopping = True
        self.sse.stop()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        await self.db.stop()
        await self.sim.close()
        await self.forecaster.close()

    # ------------------------------------------------------------------ SSE: hints only

    async def on_sse(self, name: str, data: Any) -> None:
        if name in (CONNECTED, "simulation.tick"):
            self._pending.add("full")
        elif name == "allocation.status_changed":
            self._pending.add("allocations")
        elif name == "inventory.updated":
            self._pending.add("depots")
        elif name == "simulator.notice":
            message = str((data or {}).get("message", "")) if isinstance(data, dict) else str(data)
            if "reset" in message.lower():
                self._reset_hint = True
            self._pending.add("full")
        self._wake.set()

    # ------------------------------------------------------------------ loop

    async def sync_loop(self) -> None:
        while not self._stopping:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self.settings.poll_interval_s)
            self._wake.clear()
            pending, self._pending = self._pending, set()
            try:
                due = time.time() - self._last_full_at >= self.settings.poll_interval_s
                if pending and "full" not in pending and not due and self.state.snapshot is not None:
                    await self.refresh_partial(pending)
                else:
                    if await self.refresh_full():
                        await self.maybe_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the loop must never die
                event(log, "sync_loop_error", logging.ERROR, error=f"{type(exc).__name__}: {exc}")
                await asyncio.sleep(0.5)

    async def health_loop(self) -> None:
        while not self._stopping:
            self.sim_health = await self.sim.health()
            self.prediction_up = await self.forecaster.healthy()
            self._update_gauges()
            await asyncio.sleep(5)

    # ------------------------------------------------------------------ fetching

    async def refresh_full(self) -> bool:
        async with self._refresh_lock:
            return await self._refresh_full()

    async def _refresh_full(self) -> bool:
        self._last_full_at = time.time()
        first = self.state.snapshot is None
        need_regions = first or not self.state.snapshot.regions
        paths = dict(CORE)
        if need_regions:
            paths["regions"] = "/v1/regions"
        names = list(paths)
        results = await asyncio.gather(*(self.sim.get(paths[n]) for n in names), return_exceptions=True)
        fetched = dict(zip(names, results, strict=True))
        errors = {n: r for n, r in fetched.items() if isinstance(r, BaseException)}
        if errors and self.sim.breaker.state == "closed":
            # Transient errors (error_rate fault): one more pass for just the failed resources, so a single
            # unlucky resource does not throw away a whole cycle.
            retry = await asyncio.gather(*(self.sim.get(paths[n]) for n in errors), return_exceptions=True)
            fetched.update(zip(errors, retry, strict=True))
            errors = {n: r for n, r in fetched.items() if isinstance(r, BaseException)}
        if errors:
            self.state.sync_failures += 1
            name, err = next(iter(errors.items()))
            detail = f"{err.code}: {err.message}" if isinstance(err, SimError) else f"{type(err).__name__}: {err}"
            self.state.last_sync_error = f"{name} {detail}"[:240]
            if self.state.sync_failures in (1, 5) or self.state.sync_failures % 30 == 0:
                event(log, "sync_failed", logging.WARNING, failures=self.state.sync_failures,
                      errors={n: type(e).__name__ for n, e in errors.items()}, detail=self.state.last_sync_error)
            self._update_gauges()
            return False

        stale = any(r.stale for r in fetched.values())
        self.sim.note_stale(stale)
        prev = self.state.snapshot
        instance = fetched["instance"].data
        regions = fetched["regions"].data if "regions" in fetched else prev.regions  # type: ignore[union-attr]
        snap = Snapshot(
            instance=instance, regions=regions,
            **{n: fetched[n].data for n in CORE if n != "instance"},
            fetched_at=time.time(), stale=stale,
        )
        if prev is not None and self._is_reset(prev, snap):
            self.handle_reset(snap)
            prev = None
        self._reset_hint = False

        # Demand history: 2000 rows on startup / after reset, then 200 per cycle; merged by row id.
        limit = 2000 if (prev is None or not self.state.demand) else 200
        try:
            demand = await self.sim.get("/v1/demand-history", params={"limit": limit})
            new_rows = self.state.add_demand(demand.data)
            self.db.upsert_demand(new_rows)
        except SimError as exc:
            event(log, "demand_history_failed", logging.WARNING, error=exc.code)

        if self.state.sync_failures:
            event(log, "sync_recovered", after_failures=self.state.sync_failures)
        self.state.snapshot = snap
        self.state.last_sync_ok_at = snap.fetched_at
        self.state.sync_failures = 0
        self.state.last_sync_error = None
        set_tick(snap.tick)
        self._update_gauges()
        return True

    async def refresh_partial(self, kinds: set[str]) -> None:
        """SSE said allocations or depot inventory changed: re-fetch just that resource."""
        async with self._refresh_lock:
            snap = self.state.snapshot
            if snap is None:
                return
            changes: dict[str, Any] = {}
            for kind in kinds & set(PARTIAL):
                try:
                    changes[kind] = (await self.sim.get(PARTIAL[kind])).data
                except SimError:
                    return
            if changes:
                self.state.snapshot = snap.replace(**changes)

    def _is_reset(self, prev: Snapshot, snap: Snapshot) -> bool:
        if snap.tick < prev.tick:
            return True
        # The SSE notice may arrive after a poll already caught the reset; don't clear state twice.
        if self._reset_hint and time.time() - self._last_reset_at > 3.0:
            return True
        prev_max = max((a["id"] for a in prev.allocations), default=0)
        new_max = max((a["id"] for a in snap.allocations), default=0)
        return new_max < prev_max

    def handle_reset(self, snap: Snapshot) -> None:
        event(log, "simulator_reset_detected", logging.WARNING, tick=snap.tick)
        self._last_reset_at = time.time()
        self.state.reset()
        self.recs.on_reset()
        self.db.clear_demand()
        self.plan = None
        self.last_cycle_tick = None

    # ------------------------------------------------------------------ decision cycle

    def auto_blocked(self) -> str | None:
        if self.sim.breaker.state != "closed":
            return "circuit breaker open"
        if self.sim.stale:
            return "simulator data is stale"
        if self.degraded()[0]:
            return "simulator sync failing"
        return None

    async def maybe_cycle(self, force: bool = False) -> None:
        snap = self.state.snapshot
        if snap is None or (snap.tick == self.last_cycle_tick and not force):
            return
        await self.run_cycle(snap)

    async def run_cycle(self, snap: Snapshot) -> None:
        started = time.perf_counter()
        async with self.recs.lock:
            try:
                demand = self.state.recent_demand(snap.tick - DEMAND_WINDOW_TICKS)
                analysis = await self.forecaster.analyze(snap, demand)
                self.state.analysis = analysis
                self.state.record_forecasts(analysis)
                plan = engine.plan(snap, analysis, skip_pairs=self.recs.open_pairs())
                self.plan = plan
                created = await self.recs.cycle(snap, plan, self.auto_blocked())
                self.cycle_error = None
                for p in analysis["pairs"]:
                    STATION_RISK.labels(p["station_id"], p["fuel"]).set(p["risk"])
                if created or plan.blocked:
                    event(log, "cycle", proposals=len(plan.proposals), created=len(created),
                          blocked=[c for *_, c in plan.blocked], fallback=analysis.get("fallback"), mode=self.recs.mode)
            except Exception as exc:
                self.cycle_error = f"{type(exc).__name__}: {exc}"
                event(log, "cycle_error", logging.ERROR, error=self.cycle_error)
                log.exception("cycle failed")
            finally:
                self.last_cycle_tick = snap.tick
                self.last_cycle_at = time.time()
                elapsed = time.perf_counter() - started
                self.last_cycle_ms = round(elapsed * 1000, 1)
                CYCLE_SECONDS.observe(elapsed)

    # ------------------------------------------------------------------ status

    def degraded(self) -> tuple[bool, str | None]:
        if self.state.snapshot is None:
            return True, self.state.last_sync_error or "waiting for first successful sync"
        if self.sim.breaker.state == "open":
            return True, f"circuit breaker open ({self.sim.last_error or self.state.last_sync_error})"
        age = time.time() - (self.state.last_sync_ok_at or 0)
        if age > self.settings.degraded_after_s:
            return True, self.state.last_sync_error or f"no successful sync for {age:.0f}s"
        return False, None

    def data_age(self) -> float | None:
        if self.state.last_sync_ok_at is None:
            return None
        return round(time.time() - self.state.last_sync_ok_at, 1)

    def _update_gauges(self) -> None:
        snap = self.state.snapshot
        degraded, _ = self.degraded()
        DEGRADED.set(1 if degraded else 0)
        age = self.data_age()
        if age is not None:
            DATA_AGE.set(age)
        if snap is not None:
            SIM_TICK.set(snap.tick)
            m = snap.metrics or {}
            if "service_level" in m:
                SERVICE_LEVEL.set(float(m["service_level"]))
                UNMET_LITERS.set(float(m.get("unmet_demand_liters", 0)))
                ALLOCATION_FAILURES.set(float(m.get("allocation_failures", 0)))
