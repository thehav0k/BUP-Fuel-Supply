"""The last good state, demand history and forecast log, all in memory. The API only ever reads from here."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fuelcore import FUELS, ticks_per_hour

MAX_HISTORY_TICKS = 1000
STATION_ORDER = ("station-mirpur", "station-tongi", "station-karnaphuli", "station-coxsbazar")
IN_FLIGHT = ("PENDING", "IN_TRANSIT")


@dataclass
class Snapshot:
    instance: dict[str, Any]
    regions: list[dict[str, Any]]
    depots: list[dict[str, Any]]
    stations: list[dict[str, Any]]
    routes: list[dict[str, Any]]
    supply_arrivals: list[dict[str, Any]]
    events: list[dict[str, Any]]
    allocations: list[dict[str, Any]]
    metrics: dict[str, Any]
    fetched_at: float = field(default_factory=time.time)
    stale: bool = False

    def __post_init__(self) -> None:
        self.stations = sorted(
            self.stations, key=lambda s: (STATION_ORDER.index(s["id"]) if s["id"] in STATION_ORDER else 99, s["id"])
        )
        self.depot_by_id = {d["id"]: d for d in self.depots}
        self.station_by_id = {s["id"]: s for s in self.stations}
        self.route_by_id = {r["id"]: r for r in self.routes}
        self.region_by_id = {r["id"]: r for r in self.regions}

    def replace(self, **changes: Any) -> Snapshot:
        data = {k: getattr(self, k) for k in (
            "instance", "regions", "depots", "stations", "routes", "supply_arrivals", "events", "allocations",
            "metrics", "fetched_at", "stale",
        )}
        data.update(changes)
        return Snapshot(**data)

    @property
    def tick(self) -> int:
        return int(self.instance["tick"])

    @property
    def tick_minutes(self) -> float:
        return float(self.instance.get("tick_minutes") or 15)

    @property
    def ticks_per_hour(self) -> float:
        return ticks_per_hour(self.tick_minutes)

    @property
    def sim_time(self) -> str:
        return str(self.instance.get("sim_time"))

    def in_flight(self) -> list[dict[str, Any]]:
        return [a for a in self.allocations if a.get("status") in IN_FLIGHT]

    def dispatch_used(self, depot_id: str) -> float:
        """What the simulator counts against dispatch_capacity_per_tick right now (verified: created this tick)."""
        return sum(
            float(a["quantity"]) for a in self.allocations
            if a.get("source_depot_id") == depot_id and a.get("status") in IN_FLIGHT
            and int(a.get("created_tick", -1)) == self.tick
        )

    def inbound(self, station_id: str, fuel: str) -> float:
        return sum(
            float(a["quantity"]) for a in self.allocations
            if a.get("destination_station_id") == station_id and a.get("fuel_type") == fuel
            and a.get("status") in IN_FLIGHT
        )

    def routes_to(self, station_id: str) -> list[dict[str, Any]]:
        return sorted(
            (r for r in self.routes if r["destination_station_id"] == station_id),
            key=lambda r: (r["transit_ticks"], r["id"]),
        )

    def primary_route(self, station_id: str) -> dict[str, Any] | None:
        routes = self.routes_to(station_id)
        return routes[0] if routes else None

    def scheduled_disruption(self, route_id: str) -> dict[str, Any] | None:
        """A route_disruption event that has not been applied yet but covers the current tick or later."""
        now = self.tick
        best = None
        for e in self.events:
            if e.get("type") != "route_disruption" or e.get("status") == "RESOLVED":
                continue
            ids = (e.get("parameters") or {}).get("route_ids") or []
            if ids and route_id not in ids:
                continue
            if e["end_tick"] <= now:
                continue
            if best is None or e["start_tick"] < best["start_tick"]:
                best = e
        return best

    def disruption_starts_now(self, route_id: str) -> bool:
        """A disruption starting at the current tick makes an allocation created now FAIL at departure."""
        e = self.scheduled_disruption(route_id)
        # While RUNNING the tick may advance before our POST lands, so look one tick ahead.
        lookahead = 1 if self.instance.get("status") == "RUNNING" else 0
        return e is not None and e.get("status") == "SCHEDULED" and e["start_tick"] <= self.tick + lookahead


class StateStore:
    def __init__(self) -> None:
        self.snapshot: Snapshot | None = None
        self.last_sync_ok_at: float | None = None
        self.last_sync_error: str | None = None
        self.sync_failures = 0
        self.run_id = 1
        self.analysis: dict[str, Any] | None = None
        self.demand: dict[tuple[str, str], dict[int, dict[str, Any]]] = defaultdict(dict)
        self.forecast_log: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
        self.max_demand_id = 0

    def reset(self) -> None:
        self.snapshot = None
        self.analysis = None
        self.demand.clear()
        self.forecast_log.clear()
        self.max_demand_id = 0
        self.run_id += 1

    def add_demand(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge rows by id; returns the rows that were new."""
        new = []
        for r in rows:
            key = (r["station_id"], r["fuel_type"])
            tick = int(r["tick"])
            if tick not in self.demand[key]:
                new.append(r)
            self.demand[key][tick] = r
            self.max_demand_id = max(self.max_demand_id, int(r.get("id", 0)))
        for series in self.demand.values():
            if len(series) > MAX_HISTORY_TICKS:
                for t in sorted(series)[: len(series) - MAX_HISTORY_TICKS]:
                    del series[t]
        return new

    def recent_demand(self, since_tick: int) -> list[dict[str, Any]]:
        out = []
        for (station, fuel), series in self.demand.items():
            for t, r in series.items():
                if t >= since_tick:
                    out.append({"station_id": station, "fuel_type": fuel, "tick": t, "demand_liters": r["demand_liters"]})
        return out

    def record_forecasts(self, analysis: dict[str, Any]) -> None:
        tick = int(analysis["tick"])
        for p in analysis.get("pairs", []):
            if p.get("forecast"):
                log = self.forecast_log[(p["station_id"], p["fuel"])]
                log[tick] = float(p["forecast"][0])
                if len(log) > MAX_HISTORY_TICKS:
                    for t in sorted(log)[: len(log) - MAX_HISTORY_TICKS]:
                        del log[t]

    def pair(self, station_id: str, fuel: str) -> dict[str, Any] | None:
        if not self.analysis:
            return None
        for p in self.analysis.get("pairs", []):
            if p["station_id"] == station_id and p["fuel"] == fuel:
                return p
        return None


__all__ = ["FUELS", "IN_FLIGHT", "Snapshot", "StateStore"]
