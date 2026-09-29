"""Stockout projection and risk.

Timing (verified on the live simulator): with the instance at tick T, demand for T has not happened yet.
A shipment created at T arrives while tick T + transit is processed. Arrivals are clipped at station capacity
(overflow is lost), so the projection clips too.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

IN_FLIGHT = ("PENDING", "IN_TRANSIT")
RISK_WINDOW_HOURS = 6.0


def arrival_tick(allocation: Mapping[str, Any], routes_by_id: Mapping[str, Mapping[str, Any]]) -> int | None:
    eta = allocation.get("expected_arrival_tick")
    if eta is not None:
        return int(eta)
    route = routes_by_id.get(allocation.get("route_id", ""))
    if route is None:
        return None
    return int(allocation["created_tick"]) + int(route["transit_ticks"])


def inbound_by_tick(
    allocations: Iterable[Mapping[str, Any]],
    routes_by_id: Mapping[str, Mapping[str, Any]],
    station_id: str,
    fuel: str,
    now: int,
) -> dict[int, float]:
    out: dict[int, float] = defaultdict(float)
    for a in allocations:
        if a.get("status") not in IN_FLIGHT:
            continue
        if a.get("destination_station_id") != station_id or a.get("fuel_type") != fuel:
            continue
        eta = arrival_tick(a, routes_by_id)
        if eta is None:
            continue
        out[max(eta, now)] += float(a["quantity"])
    return dict(out)


@dataclass(frozen=True)
class Projection:
    levels: list[float]  # level at the end of each tick now..now+H-1
    ticks_to_stockout: int | None  # first tick offset whose demand cannot be fully served
    unmet: float  # projected unmet liters over the horizon


def project(
    *,
    inventory: float,
    capacity: float,
    forecast: Sequence[float],
    inbound: Mapping[int, float],
    now: int,
) -> Projection:
    level = float(inventory)
    levels: list[float] = []
    tts: int | None = None
    unmet = 0.0
    for k, demand in enumerate(forecast):
        level = min(capacity, level + inbound.get(now + k, 0.0))
        level -= demand
        if level < 0:
            unmet += -level
            level = 0.0
            if tts is None:
                tts = k
        levels.append(level)
    return Projection(levels=levels, ticks_to_stockout=tts, unmet=unmet)


def risk_score(ticks_to_stockout: int | None, lead_time: int, horizon: int, tick_minutes: float) -> float:
    """1.0 when a shipment ordered now cannot land before the stockout; 0.0 with 6 h or more of slack."""
    window = RISK_WINDOW_HOURS * 60.0 / tick_minutes
    tts = horizon if ticks_to_stockout is None else ticks_to_stockout
    return max(0.0, min(1.0, (lead_time + window - tts) / window))


def risk_level(risk: float) -> str:
    if risk >= 0.7:
        return "high"
    if risk >= 0.4:
        return "medium"
    return "low"
