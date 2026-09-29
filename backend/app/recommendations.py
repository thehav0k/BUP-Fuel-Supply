"""Recommendation lifecycle, approvals, auto mode and the decision log (PRD 5.4).

OPEN -> SUBMITTING -> SUBMITTED        approved (operator) or auto; POST accepted with 200/201
OPEN -> FAILED                         pre-check or 409 at approval (code logged, never blindly retried)
OPEN -> REJECTED | EXPIRED | SUPERSEDED
SUBMITTING stays SUBMITTING on 503/timeout and is replayed with the same idempotency key next cycle.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from fuelcore import risk_level

from app.config import Settings
from app.engine import MIN_SHIPMENT, Plan, Proposal, floor_to, make_key
from app.logs import event
from app.metrics import ALLOCATION_409, ALLOCATIONS_SUBMITTED, PREVENTED, RECOMMENDATIONS
from app.persistence import Persistence
from app.sim.client import SimulatorClient
from app.sim.errors import CircuitOpen, SimConflict, SimError, SimUnavailable
from app.state import Snapshot, StateStore
from app.validation import max_feasible, precheck

log = logging.getLogger("app.recommendations")

MODES = ("manual", "auto", "hybrid")
OPEN_STATES = ("OPEN", "SUBMITTING")
RESIZABLE = ("INSUFFICIENT_INVENTORY", "DISPATCH_CAPACITY_EXCEEDED", "DESTINATION_CAPACITY_EXCEEDED",
             "DESTINATION_OVERFLOW_RISK", "ROUTE_CAPACITY_EXCEEDED")
MAX_CLOSED = 400
MAX_DECISIONS = 1000


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Recommendation:
    id: str
    created_tick: int
    created_at: str
    expires_tick: int
    status: str
    station_id: str
    station_name: str
    fuel: str
    quantity: float
    route_id: str
    depot_id: str
    depot_name: str
    transit_ticks: int
    uses_backup_route: bool
    reason: str
    reason_source: str
    risk_before: float
    risk_after: float
    ticks_to_stockout_before: int | None
    ticks_to_stockout_after: int | None
    confidence: float
    fallback: bool
    caps: list[str]
    alternative: dict[str, Any] | None
    what_if: list[dict[str, Any]]
    auto_eligible: bool
    idempotency_key: str
    allocation_id: int | None = None
    allocation_status: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    run_id: int = 1
    key_sent: bool = False
    decision_id: int | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def pair(self) -> tuple[str, str]:
        return (self.station_id, self.fuel)

    def body(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "source_depot_id": self.depot_id,
            "destination_station_id": self.station_id,
            "route_id": self.route_id,
            "fuel_type": self.fuel,
            "quantity": self.quantity,
        }

    def to_api(self) -> dict[str, Any]:
        d = asdict(self)
        for internal in ("run_id", "key_sent", "decision_id", "facts"):
            d.pop(internal)
        d["risk_level_before"] = risk_level(self.risk_before)
        d["risk_level_after"] = risk_level(self.risk_after)
        return d

    def to_record(self) -> dict[str, Any]:
        d = self.to_api()
        d["key_sent"] = self.key_sent
        d["decision_id"] = self.decision_id
        return d


class RecommendationService:
    def __init__(self, settings: Settings, sim: SimulatorClient, state: StateStore, db: Persistence, explainer: Any = None):
        self.settings = settings
        self.sim = sim
        self.state = state
        self.db = db
        self.explainer = explainer
        self.mode = settings.default_mode if settings.default_mode in MODES else "manual"
        self.recs: dict[str, Recommendation] = {}
        self.decisions: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()
        self.paused_reason: str | None = None
        self.last_cycle_tick: int | None = None
        self._decision_ids = itertools.count(time.time_ns() // 1000)
        self._startup_checked = False

    # ------------------------------------------------------------------ settings

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if mode != self.mode:
            event(log, "mode_changed", old=self.mode, new=mode)
        self.mode = mode
        self.db.save_setting("mode", mode)

    def settings_view(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "hybrid_min_confidence": self.settings.hybrid_min_confidence,
            "hybrid_max_risk": self.settings.hybrid_max_risk,
        }

    def restore(self, loaded: dict[str, Any]) -> None:
        mode = loaded.get("settings", {}).get("mode")
        if mode in MODES:
            self.mode = mode
        run_id = int(loaded.get("run_id") or 0)
        if run_id:
            self.state.run_id = run_id
        for payload in loaded.get("recommendations", []):
            data = {k: v for k, v in payload.items() if k in Recommendation.__dataclass_fields__}
            data["run_id"] = payload.get("_run_id", run_id)
            try:
                rec = Recommendation(**data)
            except TypeError:
                continue
            self.recs[rec.id] = rec
        self.decisions = sorted(loaded.get("decisions", []), key=lambda d: d["id"], reverse=True)[:MAX_DECISIONS]
        if self.decisions:
            self._decision_ids = itertools.count(max(time.time_ns() // 1000, self.decisions[0]["id"] + 1))

    # ------------------------------------------------------------------ views

    def open_recs(self) -> list[Recommendation]:
        items = [r for r in self.recs.values() if r.status in OPEN_STATES and r.run_id == self.state.run_id]
        return sorted(items, key=lambda r: (-r.risk_before, r.created_tick))

    def all_recs(self, limit: int = 200) -> list[Recommendation]:
        items = sorted(self.recs.values(), key=lambda r: (r.status not in OPEN_STATES, -r.created_tick, r.id))
        return items[:limit]

    def open_pairs(self) -> set[tuple[str, str]]:
        return {r.pair for r in self.open_recs()}

    def used_keys(self, snap: Snapshot | None) -> set[str]:
        keys = {r.idempotency_key for r in self.recs.values() if r.run_id == self.state.run_id}
        if snap is not None:
            keys |= {a["idempotency_key"] for a in snap.allocations}
        return keys

    # ------------------------------------------------------------------ decisions

    def _decide(self, rec: Recommendation, action: str, actor: str, tick: int | None, **extra: Any) -> dict[str, Any]:
        d = {
            "id": next(self._decision_ids),
            "recommendation_id": rec.id,
            "action": action,
            "actor": actor,
            "tick": tick,
            "created_at": now_iso(),
            "station_id": rec.station_id,
            "fuel": rec.fuel,
            "quantity": rec.quantity,
            "route_id": rec.route_id,
            "allocation_id": rec.allocation_id,
            "allocation_status": rec.allocation_status,
            "failure_code": rec.failure_code,
            "failure_reason": rec.failure_message,
            "note": None,
            "run_id": rec.run_id,
        }
        d.update(extra)
        self.decisions.insert(0, d)
        del self.decisions[MAX_DECISIONS:]
        rec.decision_id = d["id"]
        self.db.save_decision(d, rec.run_id)
        event(log, "decision", action=action, actor=actor, rec=rec.id, station=rec.station_id, fuel=rec.fuel,
              quantity=rec.quantity, allocation_id=rec.allocation_id, failure_code=rec.failure_code)
        return d

    def _update_decision(self, rec: Recommendation) -> None:
        for d in self.decisions:
            if d["id"] == rec.decision_id:
                d.update(allocation_id=rec.allocation_id, allocation_status=rec.allocation_status,
                         failure_code=rec.failure_code, failure_reason=rec.failure_message,
                         quantity=rec.quantity)
                self.db.save_decision(d, rec.run_id)
                return

    def _save(self, rec: Recommendation) -> None:
        self.db.save_recommendation(rec.to_record(), rec.run_id)

    def _close(self, rec: Recommendation, status: str, outcome: str) -> None:
        rec.status = status
        RECOMMENDATIONS.labels(outcome).inc()
        self._save(rec)

    # ------------------------------------------------------------------ lifecycle

    def on_reset(self) -> None:
        for rec in self.recs.values():
            if rec.status in OPEN_STATES:
                rec.status = "EXPIRED"
                rec.failure_message = "simulator reset"
                self._save(rec)
        self.paused_reason = None
        self.last_cycle_tick = None
        event(log, "recommendations_cleared_on_reset")

    def check_startup_run(self, snap: Snapshot) -> None:
        """After a backend restart, detect whether the simulator was reset meanwhile (allocation ids reused)."""
        if self._startup_checked:
            return
        self._startup_checked = True
        by_id = {a["id"]: a for a in snap.allocations}
        for rec in self.recs.values():
            if rec.run_id != self.state.run_id or rec.allocation_id is None:
                continue
            alloc = by_id.get(rec.allocation_id)
            if alloc is None or alloc.get("idempotency_key") != rec.idempotency_key:
                event(log, "new_run_detected_on_startup")
                self.state.run_id += 1
                return

    async def cycle(self, snap: Snapshot, plan: Plan, auto_blocked: str | None) -> list[Recommendation]:
        """Runs once per tick under the decision lock."""
        tick = snap.tick
        self.check_startup_run(snap)
        self.refresh_allocation_status(snap)
        await self._replay_submitting(snap, auto_blocked)

        for rec in list(self.open_recs()):
            if rec.status != "OPEN":
                continue
            if tick >= rec.expires_tick:
                self._close(rec, "EXPIRED", "expired")
                self._decide(rec, "expired", "system", tick)
                continue
            rejection = precheck(rec.body(), snap, used_keys=self.used_keys(snap) - {rec.idempotency_key})
            if rejection is not None:
                rec.failure_code, rec.failure_message = rejection.code, rejection.message
                self._close(rec, "SUPERSEDED", "superseded")
                self._decide(rec, "superseded", "system", tick)

        created = []
        used = self.used_keys(snap)
        open_pairs = self.open_pairs()
        for p in plan.proposals:
            if (p.station_id, p.fuel) in open_pairs:
                continue
            key = make_key(tick, p.station_id, p.fuel, p.route_id, used)
            used.add(key)
            rec = self._from_proposal(p, tick, key)
            self.recs[rec.id] = rec
            RECOMMENDATIONS.labels("created").inc()
            self._save(rec)
            created.append(rec)
        if created and self.explainer is not None:
            self.explainer.schedule(created, self._save)

        self.paused_reason = auto_blocked if self.mode != "manual" else None
        if self.mode != "manual" and auto_blocked is None:
            for rec in self.open_recs():
                if rec.status == "OPEN" and (self.mode == "auto" or rec.auto_eligible):
                    await self._submit(rec, snap, actor="auto")
        self._trim()
        self.last_cycle_tick = tick
        return created

    def _from_proposal(self, p: Proposal, tick: int, key: str) -> Recommendation:
        eligible = (not p.fallback and p.confidence >= self.settings.hybrid_min_confidence
                    and p.risk_before < self.settings.hybrid_max_risk)
        return Recommendation(
            id=f"rec-{uuid.uuid4().hex[:10]}",
            created_tick=tick,
            created_at=now_iso(),
            expires_tick=tick + self.settings.rec_expiry_ticks,
            status="OPEN",
            station_id=p.station_id,
            station_name=p.station_name,
            fuel=p.fuel,
            quantity=p.quantity,
            route_id=p.route_id,
            depot_id=p.depot_id,
            depot_name=p.depot_name,
            transit_ticks=p.transit_ticks,
            uses_backup_route=p.uses_backup_route,
            reason=p.reason,
            reason_source="template",
            risk_before=round(p.risk_before, 4),
            risk_after=round(p.risk_after, 4),
            ticks_to_stockout_before=p.tts_before,
            ticks_to_stockout_after=p.tts_after,
            confidence=round(p.confidence, 4),
            fallback=p.fallback,
            caps=p.caps,
            alternative=p.alternative,
            what_if=p.what_if,
            auto_eligible=eligible,
            idempotency_key=key,
            run_id=self.state.run_id,
            facts=p.facts,
        )

    def _trim(self) -> None:
        closed = [r for r in self.recs.values() if r.status not in OPEN_STATES]
        if len(closed) > MAX_CLOSED:
            closed.sort(key=lambda r: (r.created_tick, r.created_at))
            for r in closed[: len(closed) - MAX_CLOSED]:
                self.recs.pop(r.id, None)

    def refresh_allocation_status(self, snap: Snapshot) -> None:
        by_key = {a["idempotency_key"]: a for a in snap.allocations}
        for rec in self.recs.values():
            if rec.run_id != self.state.run_id or not rec.key_sent:
                continue
            alloc = by_key.get(rec.idempotency_key)
            if alloc is None:
                continue
            changed = rec.allocation_id != alloc["id"] or rec.allocation_status != alloc["status"]
            if changed:
                rec.allocation_id = alloc["id"]
                rec.allocation_status = alloc["status"]
                if alloc["status"] == "FAILED":
                    rec.failure_code = alloc.get("failure_reason") or "FAILED"
                    rec.failure_message = "allocation failed at departure"
                if rec.status == "SUBMITTING":
                    rec.status = "SUBMITTED"
                self._save(rec)
                self._update_decision(rec)

    async def _replay_submitting(self, snap: Snapshot, auto_blocked: str | None) -> None:
        """SUBMITTING recs whose POST outcome is unknown: replay with the same key (safe)."""
        if auto_blocked == "circuit breaker open":
            return
        for rec in self.open_recs():
            if rec.status == "SUBMITTING":
                await self._post(rec, snap.tick, actor=None)

    # ------------------------------------------------------------------ operator actions

    async def approve(self, rec_id: str, fresh: Snapshot | None) -> tuple[bool, Recommendation, dict[str, str] | None]:
        rec = self.recs[rec_id]
        if fresh is None:
            return False, rec, {"code": "NO_STATE", "message": "no simulator state available yet"}
        return await self._submit(rec, fresh, actor="operator")

    def reject(self, rec_id: str, note: str | None, tick: int | None) -> Recommendation:
        rec = self.recs[rec_id]
        self._close(rec, "REJECTED", "rejected")
        self._decide(rec, "rejected", "operator", tick, note=note)
        return rec

    def record_cancel(self, alloc: dict[str, Any], tick: int | None) -> None:
        for rec in self.recs.values():
            if rec.allocation_id == alloc["id"] and rec.run_id == self.state.run_id:
                rec.allocation_status = alloc["status"]
                self._save(rec)
                self._update_decision(rec)
                self._decide(rec, "cancelled", "operator", tick)
                return

    async def _submit(
        self, rec: Recommendation, snap: Snapshot, actor: str
    ) -> tuple[bool, Recommendation, dict[str, str] | None]:
        """Re-check against the given (fresh) state, resize if the state moved, then POST."""
        tick = snap.tick
        used = self.used_keys(snap) - {rec.idempotency_key}
        rejection = precheck(rec.body(), snap, used_keys=used)
        if rejection is not None and rejection.code in RESIZABLE and not rec.key_sent:
            feasible = floor_to(max_feasible(rec.body(), snap))
            if feasible >= MIN_SHIPMENT:
                old = rec.quantity
                rec.quantity = min(rec.quantity, feasible)
                rec.caps = [*rec.caps, f"resized {old:,.0f} -> {rec.quantity:,.0f} L at approval ({rejection.code})"]
                rejection = precheck(rec.body(), snap, used_keys=used)
        if rejection is not None:
            PREVENTED.labels(rejection.code).inc()
            rec.failure_code, rec.failure_message = rejection.code, rejection.message
            self._close(rec, "FAILED", "failed")
            self._decide(rec, "approved" if actor == "operator" else "auto", actor, tick)
            return False, rec, {"code": rejection.code, "message": rejection.message}

        rec.status = "SUBMITTING"
        rec.key_sent = True
        self._decide(rec, "approved" if actor == "operator" else "auto", actor, tick)
        RECOMMENDATIONS.labels("approved" if actor == "operator" else "auto").inc()
        return await self._post(rec, tick, actor)

    async def _post(
        self, rec: Recommendation, tick: int, actor: str | None
    ) -> tuple[bool, Recommendation, dict[str, str] | None]:
        try:
            resp = await self.sim.create_allocation(rec.body())
        except SimConflict as exc:
            ALLOCATION_409.labels(exc.code).inc()
            ALLOCATIONS_SUBMITTED.labels("conflict").inc()
            rec.failure_code, rec.failure_message = exc.code, exc.message
            self._close(rec, "FAILED", "failed")
            self._update_decision(rec)
            event(log, "allocation_conflict", logging.WARNING, code=exc.code, rec=rec.id, key=rec.idempotency_key)
            return False, rec, {"code": exc.code, "message": exc.message}
        except (SimUnavailable, CircuitOpen) as exc:
            ALLOCATIONS_SUBMITTED.labels("unavailable").inc()
            rec.failure_code = exc.code
            rec.failure_message = f"simulator unavailable; will replay with the same key ({exc.message})"
            self._save(rec)
            self._update_decision(rec)
            return False, rec, {"code": exc.code, "message": rec.failure_message}
        except SimError as exc:
            ALLOCATIONS_SUBMITTED.labels("error").inc()
            rec.failure_code, rec.failure_message = exc.code, exc.message
            self._close(rec, "FAILED", "failed")
            self._update_decision(rec)
            return False, rec, {"code": exc.code, "message": exc.message}

        alloc = resp.data
        ALLOCATIONS_SUBMITTED.labels("ok").inc()
        rec.status = "SUBMITTED"
        rec.allocation_id = alloc.get("id")
        rec.allocation_status = alloc.get("status")
        rec.failure_code = rec.failure_message = None
        self._save(rec)
        self._update_decision(rec)
        event(log, "allocation_created", rec=rec.id, allocation_id=rec.allocation_id, http=resp.status,
              key=rec.idempotency_key, quantity=rec.quantity)
        return True, rec, None
