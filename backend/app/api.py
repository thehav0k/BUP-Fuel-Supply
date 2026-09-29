"""Dashboard API (PRD 5.6) and demo controls (PRD 9.5). Reads are served from memory."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app import views
from app.runtime import Runtime
from app.sim.errors import SimError, SimUnavailable

router = APIRouter()
demo = APIRouter(prefix="/api/demo", tags=["demo"])


def rt(request: Request) -> Runtime:
    return request.app.state.runtime


def fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


class RejectBody(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class SettingsBody(BaseModel):
    mode: Literal["manual", "auto", "hybrid"] | None = None


class EventBody(BaseModel):
    type: Literal["demand_spike", "route_disruption", "station_outage", "depot_constraint", "shipment_delay",
                  "supply_shortfall"]
    start_tick: int | None = Field(default=None, ge=0)
    duration_ticks: int = Field(gt=0)
    parameters: dict[str, Any] = {}


class FaultBody(BaseModel):
    type: Literal["latency", "unavailable", "error_rate", "stale_data", "stream_disconnect"]
    duration_seconds: int = Field(gt=0, le=3600)
    parameters: dict[str, Any] = {}


class StepBody(BaseModel):
    count: int = Field(default=1, ge=1, le=200)


@router.get("/health", tags=["health"])
def health(request: Request) -> dict[str, Any]:
    return views.health_view(rt(request))


@router.get("/api/state", tags=["dashboard"])
def state(request: Request) -> dict[str, Any]:
    return views.state_view(rt(request))


@router.get("/api/forecast", tags=["dashboard"])
def forecast(request: Request, station_id: str = Query(...)) -> dict[str, Any]:
    out = views.forecast_view(rt(request), station_id)
    if out is None:
        raise fail(404, "NOT_FOUND", f"unknown station {station_id}")
    return out


@router.get("/api/recommendations", tags=["recommendations"])
def recommendations(request: Request, status: Literal["open", "all"] = "open") -> dict[str, Any]:
    r = rt(request)
    items = r.recs.open_recs() if status == "open" else r.recs.all_recs()
    snap = r.state.snapshot
    return {"mode": r.recs.mode, "tick": snap.tick if snap else None, "items": [x.to_api() for x in items]}


@router.post("/api/recommendations/{rec_id}/approve", tags=["recommendations"])
async def approve(request: Request, rec_id: str) -> dict[str, Any]:
    r = rt(request)
    rec = r.recs.recs.get(rec_id)
    if rec is None:
        raise fail(404, "NOT_FOUND", f"unknown recommendation {rec_id}")
    if rec.status != "OPEN":
        raise fail(409, "NOT_OPEN", f"recommendation is {rec.status}")
    # Re-check against fresh state: force a full re-fetch; fall back to the last good state if it fails.
    await r.refresh_full()
    async with r.recs.lock:
        if rec.status != "OPEN":
            raise fail(409, "NOT_OPEN", f"recommendation is {rec.status}")
        ok, rec, error = await r.recs.approve(rec_id, r.state.snapshot)
    return {"ok": ok, "recommendation": rec.to_api(), "error": error}


@router.post("/api/recommendations/{rec_id}/reject", tags=["recommendations"])
async def reject(request: Request, rec_id: str, body: RejectBody | None = None) -> dict[str, Any]:
    r = rt(request)
    rec = r.recs.recs.get(rec_id)
    if rec is None:
        raise fail(404, "NOT_FOUND", f"unknown recommendation {rec_id}")
    async with r.recs.lock:
        if rec.status != "OPEN":
            raise fail(409, "NOT_OPEN", f"recommendation is {rec.status}")
        snap = r.state.snapshot
        rec = r.recs.reject(rec_id, body.note if body else None, snap.tick if snap else None)
    return {"ok": True, "recommendation": rec.to_api(), "error": None}


@router.get("/api/allocations", tags=["allocations"])
def allocations(request: Request, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    return {"items": views.allocations_view(rt(request), limit)}


@router.post("/api/allocations/{allocation_id}/cancel", tags=["allocations"])
async def cancel(request: Request, allocation_id: int) -> dict[str, Any]:
    r = rt(request)
    try:
        resp = await r.sim.cancel_allocation(allocation_id)
    except SimUnavailable as exc:
        return {"ok": False, "allocation": None, "error": {"code": exc.code, "message": exc.message}}
    except SimError as exc:
        return {"ok": False, "allocation": None, "error": {"code": exc.code, "message": exc.message}}
    snap = r.state.snapshot
    r.recs.record_cancel(resp.data, snap.tick if snap else None)
    await r.refresh_full()
    return {"ok": True, "allocation": resp.data, "error": None}


@router.get("/api/decisions", tags=["decisions"])
def decisions(request: Request, limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    items = [{k: v for k, v in d.items() if k != "run_id"} for d in rt(request).recs.decisions[:limit]]
    return {"items": items}


@router.get("/api/events", tags=["events"])
def events(request: Request) -> dict[str, Any]:
    return views.events_view(rt(request))


@router.get("/api/settings", tags=["settings"])
def get_settings(request: Request) -> dict[str, Any]:
    return rt(request).recs.settings_view()


@router.put("/api/settings", tags=["settings"])
async def put_settings(request: Request, body: SettingsBody) -> dict[str, Any]:
    r = rt(request)
    if body.mode is not None:
        r.recs.set_mode(body.mode)
        if body.mode != "manual":
            # Act on already-open recommendations right away instead of waiting for the next tick.
            await r.refresh_full()
            snap = r.state.snapshot
            if snap is not None and r.plan is not None:
                async with r.recs.lock:
                    blocked = r.auto_blocked()
                    r.recs.paused_reason = blocked
                    if blocked is None:
                        await r.recs.submit_auto(snap)
    return r.recs.settings_view()


# ---------------------------------------------------------------------- demo controls (proxy /admin/*)


async def _admin(request: Request, method: str, path: str, json: Any = None) -> Any:
    r = rt(request)
    if not r.settings.enable_demo_controls:
        raise fail(403, "DEMO_CONTROLS_DISABLED", "set ENABLE_DEMO_CONTROLS=true to use demo controls")
    try:
        return await r.sim.admin(method, path, json)
    except SimError as exc:
        raise fail(exc.status or 502, exc.code, exc.message) from exc


async def _after_admin(request: Request) -> None:
    r = rt(request)
    if await r.refresh_full():
        await r.maybe_cycle()


@demo.post("/run")
async def demo_run(request: Request) -> Any:
    out = await _admin(request, "POST", "/admin/run")
    await _after_admin(request)
    return out


@demo.post("/pause")
async def demo_pause(request: Request) -> Any:
    out = await _admin(request, "POST", "/admin/pause")
    await _after_admin(request)
    return out


@demo.post("/step")
async def demo_step(request: Request, body: StepBody | None = None) -> Any:
    count = body.count if body else 1
    out: Any = None
    for _ in range(count):
        out = await _admin(request, "POST", "/admin/step")
        await _after_admin(request)
    return out


@demo.post("/reset")
async def demo_reset(request: Request) -> Any:
    out = await _admin(request, "POST", "/admin/reset")
    await _after_admin(request)
    return out


@demo.post("/events")
async def demo_event(request: Request, body: EventBody) -> Any:
    payload = body.model_dump()
    if payload["start_tick"] is None:
        snap = rt(request).state.snapshot
        payload["start_tick"] = snap.tick if snap else 0
    out = await _admin(request, "POST", "/admin/events", payload)
    await _after_admin(request)
    return out


@demo.get("/faults")
async def demo_faults(request: Request) -> Any:
    return await _admin(request, "GET", "/admin/faults")


@demo.post("/faults")
async def demo_fault(request: Request, body: FaultBody) -> Any:
    return await _admin(request, "POST", "/admin/faults", body.model_dump())


@demo.post("/faults/clear")
async def demo_faults_clear(request: Request) -> Any:
    return await _admin(request, "POST", "/admin/faults/clear")
