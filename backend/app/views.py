"""Build API responses (docs/api-contract.md) from the in-memory state. No I/O here."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from app.runtime import Runtime
from app.state import IN_FLIGHT
from fuelcore import FUELS, arrival_tick, parse_sim_time, risk_level, time_at

VERSION = "1.0.0"


def _iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(ts, UTC).isoformat()


def state_view(rt: Runtime) -> dict[str, Any]:
    snap = rt.state.snapshot
    degraded, reason = rt.degraded()
    analysis = rt.state.analysis or {}
    fallback = bool(analysis.get("fallback")) if analysis else rt.forecaster.fallback
    base = {
        "tick": None, "sim_time": None, "sim_status": None, "tick_minutes": 15, "ticks_per_hour": 4,
        "fetched_at": _iso(rt.state.last_sync_ok_at), "data_age_s": rt.data_age(),
        "stale": rt.sim.stale, "degraded": degraded, "degraded_reason": reason, "fallback": fallback,
        "mode": rt.recs.mode, "metrics": None, "stations": [], "depots": [], "routes": [], "alerts": [],
        "counts": {"open_recommendations": len(rt.recs.open_recs()), "pending_allocations": 0,
                   "in_transit_allocations": 0},
    }
    if snap is None:
        base["alerts"] = _status_alerts(rt, degraded, reason, fallback)
        return base

    pairs = {(p["station_id"], p["fuel"]): p for p in analysis.get("pairs", [])} if analysis else {}
    tph = snap.ticks_per_hour
    stations = []
    for st in snap.stations:
        primary = snap.primary_route(st["id"])
        fuels = []
        upcoming = None
        for fuel in FUELS:
            if fuel not in st["capacity"]:
                continue
            p = pairs.get((st["id"], fuel), {})
            cap = float(st["capacity"][fuel])
            inv = float(st["inventory"].get(fuel, 0))
            inbound = [
                {"allocation_id": a["id"], "quantity": a["quantity"], "eta_tick": arrival_tick(a, snap.route_by_id),
                 "status": a["status"], "route_id": a["route_id"]}
                for a in snap.allocations
                if a.get("destination_station_id") == st["id"] and a.get("fuel_type") == fuel
                and a.get("status") in IN_FLIGHT
            ]
            upcoming = upcoming or p.get("upcoming_spike")
            risk = float(p.get("risk", 0.0))
            fuels.append({
                "fuel": fuel, "inventory": round(inv, 1), "capacity": cap,
                "fill_pct": round(100 * inv / cap, 1) if cap else 0.0,
                "inbound_liters": round(sum(i["quantity"] for i in inbound), 1), "inbound": inbound,
                "ticks_to_stockout": p.get("ticks_to_stockout"), "hours_to_stockout": p.get("hours_to_stockout"),
                "risk": risk, "risk_level": risk_level(risk),
                "spike": bool(p.get("spike")), "spike_reason": p.get("spike_reason"),
                "forecast_next_hour": p.get("forecast_next_hour", 0.0),
                "calibration_ratio": p.get("ratio", 1.0), "confidence": p.get("confidence", 0.0),
                "lead_time_ticks": p.get("lead_time", (primary["transit_ticks"] + 1) if primary else 3),
            })
        stations.append({
            "id": st["id"], "name": st.get("name", st["id"]), "region_id": st.get("region_id"),
            "status": st.get("status"), "demand_profile": st.get("demand_profile"),
            "demand_multiplier": st.get("demand_multiplier", 1.0),
            "spike": any(f["spike"] for f in fuels), "upcoming_spike": upcoming,
            "primary_route_id": primary["id"] if primary else None, "fuels": fuels,
        })

    depot_proj = {(d["depot_id"], d["fuel"]): d for d in analysis.get("depots", [])} if analysis else {}
    reserves = rt.plan.reserves if rt.plan else {}
    depots = []
    for d in snap.depots:
        fuels = []
        for fuel in FUELS:
            if fuel not in d["inventory"]:
                continue
            proj = depot_proj.get((d["id"], fuel), {})
            cap = float(d["capacity"].get(fuel, 0))
            inv = float(d["inventory"][fuel])
            fuels.append({
                "fuel": fuel, "inventory": round(inv, 1), "capacity": cap,
                "fill_pct": round(100 * inv / cap, 1) if cap else 0.0,
                "next_arrival": proj.get("next_arrival") or _next_arrival(snap, d["id"], fuel, tph),
                "projected_level_end": proj.get("projected_level_end", inv),
                "reserve_liters": reserves.get((d["id"], fuel), 0.0),
            })
        depots.append({
            "id": d["id"], "name": d.get("name", d["id"]), "region_id": d.get("region_id"), "status": d.get("status"),
            "dispatch_capacity_per_tick": d["dispatch_capacity_per_tick"],
            "dispatch_used_this_tick": round(snap.dispatch_used(d["id"]), 1), "fuels": fuels,
        })

    routes = []
    for r in snap.routes:
        src = snap.depot_by_id.get(r["source_depot_id"], {})
        dst = snap.station_by_id.get(r["destination_station_id"], {})
        disruption = snap.scheduled_disruption(r["id"])
        routes.append({
            "id": r["id"], "source_depot_id": r["source_depot_id"], "destination_station_id": r["destination_station_id"],
            "transit_ticks": r["transit_ticks"], "max_shipment": r["max_shipment"], "status": r["status"],
            "is_backup": src.get("region_id") != dst.get("region_id"),
            "scheduled_disruption": None if disruption is None
            else {"start_tick": disruption["start_tick"], "end_tick": disruption["end_tick"]},
        })

    alerts = list(rt.plan.alerts) if rt.plan else []
    alerts += _status_alerts(rt, degraded, reason, fallback)
    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["level"], 3))
    base.update(
        tick=snap.tick, sim_time=snap.sim_time, sim_status=snap.instance.get("status"),
        tick_minutes=snap.tick_minutes, ticks_per_hour=tph, metrics=snap.metrics,
        stations=stations, depots=depots, routes=routes, alerts=alerts,
    )
    base["counts"].update(
        pending_allocations=sum(1 for a in snap.allocations if a.get("status") == "PENDING"),
        in_transit_allocations=sum(1 for a in snap.allocations if a.get("status") == "IN_TRANSIT"),
    )
    return base


def _next_arrival(snap: Any, depot_id: str, fuel: str, tph: float) -> dict[str, Any] | None:
    upcoming = [s for s in snap.supply_arrivals
                if s["depot_id"] == depot_id and s["fuel_type"] == fuel and s["status"] in ("SCHEDULED", "DELAYED")]
    if not upcoming:
        return None
    s = min(upcoming, key=lambda x: x["planned_tick"])
    return {"tick": s["planned_tick"], "quantity": s["quantity"], "status": s["status"],
            "in_hours": round(max(0, s["planned_tick"] - snap.tick) / tph, 2)}


def _status_alerts(rt: Runtime, degraded: bool, reason: str | None, fallback: bool) -> list[dict[str, Any]]:
    out = []
    if degraded:
        out.append({"id": "degraded", "level": "critical", "kind": "degraded",
                    "message": f"Simulator unreachable: showing last good state. {reason or ''}".strip()})
    if rt.sim.stale:
        out.append({"id": "stale", "level": "warning", "kind": "stale",
                    "message": "Simulator reports stale data; auto submissions are paused."})
    if fallback:
        out.append({"id": "fallback", "level": "warning", "kind": "fallback",
                    "message": "Prediction service unavailable: using the uncalibrated baseline forecast."})
    return out


def forecast_view(rt: Runtime, station_id: str) -> dict[str, Any] | None:
    snap = rt.state.snapshot
    analysis = rt.state.analysis or {}
    if snap is None:
        return {"station_id": station_id, "tick": None, "tick_minutes": 15, "fallback": rt.forecaster.fallback,
                "fuels": []}
    st = snap.station_by_id.get(station_id)
    if st is None:
        return None
    base_time = parse_sim_time(snap.sim_time)
    fuels = []
    for fuel in FUELS:
        if fuel not in st["capacity"]:
            continue
        pair = rt.state.pair(station_id, fuel) or {}
        hist = rt.state.demand.get((station_id, fuel), {})
        flog = rt.state.forecast_log.get((station_id, fuel), {})
        ticks = sorted(hist)[-96:]
        history = [{"tick": t, "sim_time": hist[t]["sim_time"], "actual": round(hist[t]["demand_liters"], 2),
                    "forecast": None if t not in flog else round(flog[t], 2),
                    "unmet": round(hist[t].get("unmet_liters", 0.0), 2)} for t in ticks]
        future = []
        start = int(analysis.get("tick", snap.tick)) if analysis else snap.tick
        for k, (f, lvl) in enumerate(zip(pair.get("forecast", []), pair.get("levels", []), strict=False)):
            t = start + k
            future.append({"tick": t, "sim_time": time_at(base_time, snap.tick, t, snap.tick_minutes).isoformat(),
                           "forecast": round(f, 2), "projected_level": round(lvl, 1)})
        fuels.append({"fuel": fuel, "capacity": float(st["capacity"][fuel]),
                      "calibration_ratio": pair.get("ratio", 1.0), "confidence": pair.get("confidence", 0.0),
                      "history": history, "future": future})
    return {"station_id": station_id, "tick": snap.tick, "tick_minutes": snap.tick_minutes,
            "fallback": bool(analysis.get("fallback")), "fuels": fuels}


def allocations_view(rt: Runtime, limit: int) -> list[dict[str, Any]]:
    snap = rt.state.snapshot
    if snap is None:
        return []
    by_key = {r.idempotency_key: r.id for r in rt.recs.recs.values() if r.run_id == rt.state.run_id}
    return [dict(a, recommendation_id=by_key.get(a["idempotency_key"])) for a in snap.allocations[:limit]]


def events_view(rt: Runtime) -> dict[str, Any]:
    snap = rt.state.snapshot
    if snap is None:
        return {"tick": None, "items": []}
    return {"tick": snap.tick, "items": [dict(e, description=describe_event(e, snap)) for e in snap.events]}


def describe_event(e: dict[str, Any], snap: Any) -> str:
    p = e.get("parameters") or {}

    def names(ids: list[str], lookup: dict[str, Any], every: str) -> str:
        if not ids:
            return every
        return ", ".join(str(lookup.get(i, {}).get("name", i)) for i in ids)

    t = e.get("type")
    span = f"ticks {e['start_tick']}-{e['end_tick']}"
    if t == "demand_spike":
        where = names(p.get("station_ids") or [], snap.station_by_id, "")
        regions = names(p.get("region_ids") or [], snap.region_by_id, "")
        target = " / ".join(x for x in (where, regions) if x) or "all stations"
        return f"Demand x{p.get('multiplier', 1.5)} at {target} ({span})"
    if t == "route_disruption":
        return f"Route disrupted: {', '.join(p.get('route_ids') or []) or 'all routes'} ({span})"
    if t == "station_outage":
        return f"Station outage: {names(p.get('station_ids') or [], snap.station_by_id, 'all stations')} ({span})"
    if t == "depot_constraint":
        return f"Depot constrained: {names(p.get('depot_ids') or [], snap.depot_by_id, 'all depots')} ({span})"
    if t == "shipment_delay":
        fuels = ", ".join(p.get("fuel_types") or []) or "all fuels"
        depots = names(p.get("depot_ids") or [], snap.depot_by_id, "all depots")
        return f"Supply delayed {p.get('delay_ticks', 2)} ticks at {depots} ({fuels})"
    if t == "supply_shortfall":
        fuels = ", ".join(p.get("fuel_types") or []) or "all fuels"
        depots = names(p.get("depot_ids") or [], snap.depot_by_id, "all depots")
        return f"Supply cut to {float(p.get('factor', 0.5)):.0%} at {depots} ({fuels})"
    return f"{t} ({span})"


def health_view(rt: Runtime) -> dict[str, Any]:
    now = time.time()
    breaker = rt.sim.breaker.state
    degraded, reason = rt.degraded()
    sim_ok = rt.sim_health is not None
    sim_status = "down" if (not sim_ok and degraded) else "degraded" if (degraded or rt.sim.stale) else "up"
    sim_detail = reason or ("stale data reported" if rt.sim.stale else "in sync")
    if not sim_ok:
        sim_detail = f"/v1/health unreachable; {sim_detail}"

    db = rt.db
    db_status = {"up": "up", "down": "down", "disabled": "degraded"}[db.status]
    db_detail = {"up": "connected", "down": db.last_error or "unreachable; writes queued",
                 "disabled": "persistence disabled (DATABASE_URL empty)"}[db.status]

    pred_up = rt.prediction_up
    pred_status = "degraded" if rt.forecaster.fallback else ("up" if pred_up in (True, None) else "down")
    if pred_up is False:
        pred_status = "down"
    pred_detail = ("fallback: uncalibrated baseline in backend" if rt.forecaster.fallback else "calibrated forecasts")
    if rt.forecaster.last_error and rt.forecaster.fallback:
        pred_detail += f" ({rt.forecaster.last_error[:80]})"

    sse = rt.sse
    sse_status = "up" if sse.connected else ("down" if rt.settings.enable_sse else "degraded")

    eng_status = "up"
    eng_detail = f"mode {rt.recs.mode}"
    if rt.cycle_error:
        eng_status, eng_detail = "degraded", rt.cycle_error[:120]
    elif rt.recs.paused_reason:
        eng_status, eng_detail = "degraded", f"auto submissions paused: {rt.recs.paused_reason}"
    elif rt.last_cycle_at is None:
        eng_status, eng_detail = "degraded", "waiting for first cycle"

    components = {
        "simulator": {"status": sim_status, "detail": sim_detail, "last_ok_at": _iso(rt.sim.last_ok_at),
                      "breaker": breaker, "consecutive_failures": rt.sim.breaker.failures, "stale": rt.sim.stale,
                      "sim_health": "ok" if sim_ok else "down"},
        "database": {"status": db_status, "detail": db_detail, "last_ok_at": _iso(db.last_ok_at),
                     "pending_writes": db.queue.qsize()},
        "prediction": {"status": pred_status, "detail": pred_detail, "last_ok_at": _iso(rt.forecaster.last_ok_at),
                       "fallback": rt.forecaster.fallback, "last_latency_ms": rt.forecaster.last_latency_ms},
        "sse": {"status": sse_status, "detail": "connected" if sse.connected else (sse.last_error or "connecting"),
                "last_ok_at": _iso(sse.last_event_at), "connected": sse.connected, "reconnects": sse.reconnects,
                "last_event_at": _iso(sse.last_event_at)},
        "engine": {"status": eng_status, "detail": eng_detail, "last_ok_at": _iso(rt.last_cycle_at),
                   "mode": rt.recs.mode, "last_cycle_tick": rt.last_cycle_tick, "last_cycle_at": _iso(rt.last_cycle_at),
                   "last_cycle_ms": rt.last_cycle_ms, "paused_reason": rt.recs.paused_reason},
    }
    overall = "ok" if all(c["status"] == "up" for c in components.values()) else "degraded"
    return {"status": overall, "version": VERSION, "grafana_url": rt.settings.grafana_url,
            "uptime_s": round(now - rt.started_at, 1), "components": components}
