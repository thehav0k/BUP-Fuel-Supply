"""Pre-check an allocation in the simulator's own validation order, so we never send a request that would 409.

Simulator order: idempotency -> NOT_FOUND -> ROUTE_MISMATCH -> DEPOT_CLOSED -> STATION_CLOSED -> ROUTE_DISRUPTED
-> ROUTE_CAPACITY_EXCEEDED -> INSUFFICIENT_INVENTORY -> DISPATCH_CAPACITY_EXCEEDED -> DESTINATION_CAPACITY_EXCEEDED.

Two stricter platform rules are added (strict=True), because the simulator accepts these but loses fuel:
- ROUTE_DISRUPTION_SCHEDULED: a disruption starting this tick makes the allocation FAIL at departure.
- DESTINATION_OVERFLOW_RISK: inventory + inbound + quantity above capacity; the overflow is discarded on arrival.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from fuelcore import FUELS

from app.state import Snapshot

VALID_DEPOT_STATUS = ("OPEN", "CONSTRAINED")
EPS = 1e-6


@dataclass(frozen=True)
class Rejection:
    code: str
    message: str


@dataclass
class Committed:
    """Quantities we already committed in this cycle that the snapshot does not show yet."""

    depot_out: dict[tuple[str, str], float] = field(default_factory=lambda: defaultdict(float))
    dispatch: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    station_in: dict[tuple[str, str], float] = field(default_factory=lambda: defaultdict(float))

    def add(self, req: dict[str, Any]) -> None:
        q = float(req["quantity"])
        self.depot_out[(req["source_depot_id"], req["fuel_type"])] += q
        self.dispatch[req["source_depot_id"]] += q
        self.station_in[(req["destination_station_id"], req["fuel_type"])] += q


def precheck(
    req: dict[str, Any],
    snap: Snapshot,
    committed: Committed | None = None,
    *,
    used_keys: Collection[str] = (),
    strict: bool = True,
) -> Rejection | None:
    c = committed or Committed()
    key = req.get("idempotency_key") or ""
    qty = float(req.get("quantity") or 0)
    fuel = req.get("fuel_type")

    if not (1 <= len(key) <= 150):
        return Rejection("VALIDATION_ERROR", "idempotency_key must be 1-150 characters")
    if key in used_keys:
        return Rejection("IDEMPOTENCY_KEY_MISMATCH", f"idempotency key {key} was already used")
    if fuel not in FUELS or qty <= 0:
        return Rejection("VALIDATION_ERROR", "fuel_type must be DIESEL/PETROL/OCTANE and quantity > 0")

    depot = snap.depot_by_id.get(req.get("source_depot_id", ""))
    station = snap.station_by_id.get(req.get("destination_station_id", ""))
    route = snap.route_by_id.get(req.get("route_id", ""))
    if depot is None or station is None or route is None:
        missing = "depot" if depot is None else "station" if station is None else "route"
        return Rejection("NOT_FOUND", f"unknown {missing}")
    if route["source_depot_id"] != depot["id"] or route["destination_station_id"] != station["id"]:
        return Rejection("ROUTE_MISMATCH", f"{route['id']} does not connect {depot['id']} to {station['id']}")
    if depot.get("status") not in VALID_DEPOT_STATUS:
        return Rejection("DEPOT_CLOSED", f"{depot['id']} is {depot.get('status')}")
    if station.get("status") != "OPEN":
        return Rejection("STATION_CLOSED", f"{station['id']} is {station.get('status')}")
    if route.get("status") != "AVAILABLE":
        return Rejection("ROUTE_DISRUPTED", f"{route['id']} is {route.get('status')}")
    if strict and snap.disruption_starts_now(route["id"]):
        return Rejection("ROUTE_DISRUPTION_SCHEDULED", f"{route['id']} is scheduled to be disrupted at departure")
    if qty > float(route["max_shipment"]) + EPS:
        return Rejection("ROUTE_CAPACITY_EXCEEDED", f"{qty:.0f} L exceeds route max {route['max_shipment']:.0f} L")
    depot_inv = float(depot["inventory"].get(fuel, 0)) - c.depot_out[(depot["id"], fuel)]
    if depot_inv + EPS < qty:
        return Rejection("INSUFFICIENT_INVENTORY", f"{depot['id']} has {depot_inv:.0f} L {fuel}")
    used = snap.dispatch_used(depot["id"]) + c.dispatch[depot["id"]]
    if used + qty > float(depot["dispatch_capacity_per_tick"]) + EPS:
        return Rejection(
            "DISPATCH_CAPACITY_EXCEEDED",
            f"{depot['id']} dispatch {used:.0f} + {qty:.0f} > {depot['dispatch_capacity_per_tick']:.0f} L this tick",
        )
    st_inv = float(station["inventory"].get(fuel, 0))
    cap = float(station["capacity"].get(fuel, 0))
    if st_inv + qty > cap + EPS:
        return Rejection("DESTINATION_CAPACITY_EXCEEDED", f"{st_inv:.0f} + {qty:.0f} > capacity {cap:.0f} L")
    if strict:
        inbound = snap.inbound(station["id"], fuel) + c.station_in[(station["id"], fuel)]
        if st_inv + inbound + qty > cap + EPS:
            return Rejection(
                "DESTINATION_OVERFLOW_RISK",
                f"{st_inv:.0f} + inbound {inbound:.0f} + {qty:.0f} > capacity {cap:.0f} L (overflow would be lost)",
            )
    return None


def max_feasible(req: dict[str, Any], snap: Snapshot, committed: Committed | None = None) -> float:
    """Largest quantity that passes the quantity-dependent checks for this depot/station/route."""
    c = committed or Committed()
    fuel = req["fuel_type"]
    depot = snap.depot_by_id[req["source_depot_id"]]
    station = snap.station_by_id[req["destination_station_id"]]
    route = snap.route_by_id[req["route_id"]]
    inbound = snap.inbound(station["id"], fuel) + c.station_in[(station["id"], fuel)]
    return max(
        0.0,
        min(
            float(route["max_shipment"]),
            float(depot["inventory"].get(fuel, 0)) - c.depot_out[(depot["id"], fuel)],
            float(depot["dispatch_capacity_per_tick"]) - snap.dispatch_used(depot["id"]) - c.dispatch[depot["id"]],
            float(station["capacity"][fuel]) - float(station["inventory"].get(fuel, 0)) - inbound,
        ),
    )
