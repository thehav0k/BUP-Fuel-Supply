"""One call that turns a network snapshot plus recent demand into forecasts, risk and depot projections.

The prediction service runs it with calibration enabled. The backend runs it with calibration disabled as the
rule-based fallback when the prediction service is down, so both paths share the exact same formulas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .forecast import CALIBRATION_WINDOW, SPIKE_TICKS, MultiplierTimeline, baseline_series, calibrate
from .projection import inbound_by_tick, project, risk_level, risk_score
from .world import FUELS, parse_sim_time, ticks_per_hour

DEFAULT_HORIZON = 48


def best_route(routes: list[Mapping[str, Any]], station_id: str) -> Mapping[str, Any] | None:
    """Shortest-transit route to the station, preferring AVAILABLE ones."""
    to_station = [r for r in routes if r["destination_station_id"] == station_id]
    if not to_station:
        return None
    available = [r for r in to_station if r.get("status") == "AVAILABLE"]
    pool = available or to_station
    return min(pool, key=lambda r: (r["transit_ticks"], r["id"]))


def lead_time(routes: list[Mapping[str, Any]], station_id: str) -> int:
    r = best_route(routes, station_id)
    return (int(r["transit_ticks"]) if r else 2) + 1


def analyze(request: Mapping[str, Any], *, calibrate_enabled: bool = True) -> dict[str, Any]:
    now = int(request["tick"])
    tick_minutes = float(request.get("tick_minutes") or 15)
    horizon = int(request.get("horizon") or DEFAULT_HORIZON)
    base_time = parse_sim_time(request["sim_time"])
    tph = ticks_per_hour(tick_minutes)

    regions = {r["id"]: float(r.get("demand_factor", 1.0)) for r in request.get("regions", [])}
    routes = list(request.get("routes", []))
    routes_by_id = {r["id"]: r for r in routes}
    events = list(request.get("events", []))
    allocations = list(request.get("allocations", []))

    history: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for row in request.get("demand", []):
        history[(row["station_id"], row["fuel_type"])][int(row["tick"])] = float(row["demand_liters"])

    past_ticks = list(range(now - CALIBRATION_WINDOW, now))
    future_ticks = list(range(now, now + horizon))

    pairs: list[dict[str, Any]] = []
    for st in request.get("stations", []):
        timeline = MultiplierTimeline(st, events)
        region_factor = regions.get(st.get("region_id", ""), 1.0)
        lead = lead_time(routes, st["id"])
        upcoming = timeline.upcoming(now, horizon)
        multiplier_now = timeline.at(now)
        for fuel in FUELS:
            if fuel not in st.get("capacity", {}):
                continue
            hist = history.get((st["id"], fuel), {})
            observed = [t for t in past_ticks if t in hist]
            recent_mean = (sum(hist[t] for t in observed) / len(observed)) if observed else None
            common = dict(
                profile=st.get("demand_profile", ""),
                fuel=fuel,
                region_factor=region_factor,
                timeline=timeline,
                base_time=base_time,
                base_tick=now,
                tick_minutes=tick_minutes,
                fallback_per_tick=recent_mean,
            )
            past_base = baseline_series(ticks=observed, **common)
            cal = calibrate([hist[t] for t in observed], past_base, enabled=calibrate_enabled)
            base = baseline_series(ticks=future_ticks, **common)
            forecast = [b * cal.ratio for b in base]

            inbound = inbound_by_tick(allocations, routes_by_id, st["id"], fuel, now)
            capacity = float(st["capacity"][fuel])
            inventory = float(st.get("inventory", {}).get(fuel, 0.0))
            proj = project(inventory=inventory, capacity=capacity, forecast=forecast, inbound=inbound, now=now)
            risk = risk_score(proj.ticks_to_stockout, lead, horizon, tick_minutes)
            level_at_lead = proj.levels[min(lead, horizon) - 1] if proj.levels else inventory

            spike_reason = None
            if multiplier_now > 1.0:
                spike_reason = f"demand multiplier x{multiplier_now:.2f} (demand_spike event)"
            elif cal.spike_by_ratio and cal.recent_ratio is not None:
                spike_reason = f"demand running {cal.recent_ratio:.2f}x baseline for {SPIKE_TICKS}+ ticks"

            pairs.append(
                {
                    "station_id": st["id"],
                    "fuel": fuel,
                    "capacity": capacity,
                    "inventory": inventory,
                    "inbound_liters": sum(inbound.values()),
                    "ratio": round(cal.ratio, 4),
                    "mape": None if cal.mape is None else round(cal.mape, 4),
                    "confidence": round(cal.confidence, 4),
                    "calibration_points": cal.points,
                    "spike": spike_reason is not None,
                    "spike_reason": spike_reason,
                    "upcoming_spike": upcoming,
                    "multiplier_now": multiplier_now,
                    "forecast": [round(x, 3) for x in forecast],
                    "baseline": [round(x, 3) for x in base],
                    "levels": [round(x, 3) for x in proj.levels],
                    "forecast_next_hour": round(sum(forecast[: max(1, round(tph))]), 3),
                    "ticks_to_stockout": proj.ticks_to_stockout,
                    "hours_to_stockout": None
                    if proj.ticks_to_stockout is None
                    else round(proj.ticks_to_stockout / tph, 2),
                    "projected_unmet": round(proj.unmet, 3),
                    "lead_time": lead,
                    "level_at_lead": round(level_at_lead, 3),
                    "risk": round(risk, 4),
                    "risk_level": risk_level(risk),
                }
            )

    depots = depot_projection(request, now=now, horizon=horizon, tph=tph)
    return {
        "model": "calibrated-baseline" if calibrate_enabled else "baseline",
        "calibrated": calibrate_enabled,
        "tick": now,
        "horizon": horizon,
        "pairs": pairs,
        "depots": depots,
    }


def depot_projection(request: Mapping[str, Any], *, now: int, horizon: int, tph: float) -> list[dict[str, Any]]:
    """Inventory plus scheduled arrivals. Outbound is already deducted by the simulator at allocation time."""
    arrivals: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for s in request.get("supply_arrivals", []):
        if s.get("status") in ("SCHEDULED", "DELAYED"):
            arrivals[(s["depot_id"], s["fuel_type"])].append(s)
    out = []
    for d in request.get("depots", []):
        for fuel in FUELS:
            if fuel not in d.get("inventory", {}):
                continue
            inv = float(d["inventory"][fuel])
            upcoming = sorted(arrivals.get((d["id"], fuel), []), key=lambda s: s["planned_tick"])
            by_tick: dict[int, float] = defaultdict(float)
            for s in upcoming:
                by_tick[max(int(s["planned_tick"]), now)] += float(s["quantity"])
            level, levels = inv, []
            for k in range(horizon):
                level += by_tick.get(now + k, 0.0)
                levels.append(round(level, 3))
            nxt = upcoming[0] if upcoming else None
            out.append(
                {
                    "depot_id": d["id"],
                    "fuel": fuel,
                    "inventory": inv,
                    "levels": levels,
                    "projected_level_end": levels[-1] if levels else inv,
                    "next_arrival": None
                    if nxt is None
                    else {
                        "tick": max(int(nxt["planned_tick"]), now),
                        "quantity": float(nxt["quantity"]),
                        "status": nxt["status"],
                        "in_hours": round(max(0, int(nxt["planned_tick"]) - now) / tph, 2),
                    },
                }
            )
    return out
