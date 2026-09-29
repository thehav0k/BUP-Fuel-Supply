"""Greedy per-tick allocation planner (PRD 5.3). Pure: snapshot + analysis in, proposals and alerts out.

1. Candidates: ticks_to_stockout <= lead + 2 h, or projected level at lead time below 35% of capacity.
2. Order: risk, then projected unmet liters.
3. Quantity: refill toward 85% of capacity, capped by headroom (capacity - inventory - inbound), route max,
   depot availability after the reserve, and dispatch capacity left this tick. Skip under 500 L.
4. Route: the shortest usable route whose depot can supply >= 500 L; a backup is used (and explained)
   when the primary is disrupted, about to be disrupted, or its depot is short.
5. Depot reserve: a depot keeps what its own stations need until its next supply arrival. Under scarcity
   its own stations share it in proportion to need, so no fuel sits idle while they run dry.
6. Every proposal passes the simulator-order pre-check before it is proposed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fuelcore import FUELS, inbound_by_tick, project, risk_level, risk_score

from app.metrics import PREVENTED
from app.state import Snapshot
from app.validation import Committed, precheck

TARGET_FILL = 0.85
LOW_FILL = 0.35
BUFFER_HOURS = 2.0
MIN_SHIPMENT = 500.0
ROUND_TO = 50.0
WHAT_IF_TICKS = 24


@dataclass
class Proposal:
    station_id: str
    station_name: str
    fuel: str
    depot_id: str
    depot_name: str
    route_id: str
    transit_ticks: int
    quantity: float
    uses_backup_route: bool
    backup_reason: str | None
    caps: list[str]
    reason: str
    risk_before: float
    risk_after: float
    tts_before: int | None
    tts_after: int | None
    confidence: float
    fallback: bool
    alternative: dict[str, Any] | None
    what_if: list[dict[str, Any]]
    facts: dict[str, Any] = field(default_factory=dict)  # numbers used in the reason, for LLM explanations

    def request(self, key: str) -> dict[str, Any]:
        return {
            "idempotency_key": key,
            "source_depot_id": self.depot_id,
            "destination_station_id": self.station_id,
            "route_id": self.route_id,
            "fuel_type": self.fuel,
            "quantity": self.quantity,
        }


@dataclass
class Plan:
    proposals: list[Proposal]
    alerts: list[dict[str, Any]]
    reserves: dict[tuple[str, str], float]
    blocked: list[tuple[str, str, str]]  # (station, fuel, code) stopped by pre-check


def make_key(tick: int, station_id: str, fuel: str, route_id: str, used: set[str] | frozenset[str]) -> str:
    """Deterministic idempotency key {tick}-{station}-{fuel}-{route}-{n}; n is the first unused suffix."""
    n = 0
    while True:
        key = f"{tick}-{station_id}-{fuel}-{route_id}-{n}"
        if key not in used:
            return key
        n += 1


def floor_to(q: float, step: float = ROUND_TO) -> float:
    return math.floor(q / step) * step


def _name(entity: dict[str, Any]) -> str:
    return str(entity.get("name") or entity["id"])


def _short(station_or_depot: dict[str, Any]) -> str:
    name = _name(station_or_depot)
    for suffix in (" Fuel Station", " Industrial Station", " Highway Station", " Regional Station", " Depot"):
        name = name.replace(suffix, "")
    return name


class Planner:
    def __init__(self, snap: Snapshot, analysis: dict[str, Any], *, skip_pairs: set[tuple[str, str]] | None = None):
        self.snap = snap
        self.analysis = analysis
        self.skip = skip_pairs or set()
        self.now = snap.tick
        self.tph = snap.ticks_per_hour
        self.horizon = int(analysis.get("horizon") or 48)
        self.fallback = bool(analysis.get("fallback"))
        self.pairs = {(p["station_id"], p["fuel"]): p for p in analysis.get("pairs", [])}
        self.depot_proj = {(d["depot_id"], d["fuel"]): d for d in analysis.get("depots", [])}
        self.committed = Committed()
        self.alerts: list[dict[str, Any]] = []
        self.blocked: list[tuple[str, str, str]] = []
        self.own_stations: dict[str, list[str]] = defaultdict(list)
        for st in snap.stations:
            primary = snap.primary_route(st["id"])
            if primary:
                self.own_stations[primary["source_depot_id"]].append(st["id"])

    # ------------------------------------------------------------ helpers

    def usable(self, route: dict[str, Any]) -> tuple[bool, str | None]:
        depot = self.snap.depot_by_id.get(route["source_depot_id"])
        if route.get("status") != "AVAILABLE":
            return False, f"{route['id']} is {route.get('status', 'unavailable').lower()}"
        if self.snap.disruption_starts_now(route["id"]):
            return False, f"{route['id']} is scheduled to be disrupted at departure"
        if depot is None or depot.get("status") not in ("OPEN", "CONSTRAINED"):
            return False, f"{route['source_depot_id']} is closed"
        return True, None

    def inbound_total(self, station_id: str, fuel: str) -> float:
        return self.snap.inbound(station_id, fuel) + self.committed.station_in[(station_id, fuel)]

    def depot_inventory(self, depot_id: str, fuel: str) -> float:
        depot = self.snap.depot_by_id[depot_id]
        return float(depot["inventory"].get(fuel, 0.0)) - self.committed.depot_out[(depot_id, fuel)]

    def dispatch_left(self, depot_id: str) -> float:
        depot = self.snap.depot_by_id[depot_id]
        used = self.snap.dispatch_used(depot_id) + self.committed.dispatch[depot_id]
        return float(depot["dispatch_capacity_per_tick"]) - used

    def ticks_to_next_arrival(self, depot_id: str, fuel: str) -> int:
        proj = self.depot_proj.get((depot_id, fuel))
        nxt = proj.get("next_arrival") if proj else None
        if not nxt:
            return self.horizon
        return max(0, int(nxt["tick"]) - self.now)

    def need_until_resupply(self, station_id: str, fuel: str, depot_id: str) -> float:
        """Liters this station needs before the depot's next arrival can reach it."""
        pair = self.pairs.get((station_id, fuel))
        st = self.snap.station_by_id.get(station_id)
        if pair is None or st is None or st.get("status") != "OPEN":
            return 0.0
        k = min(self.horizon, self.ticks_to_next_arrival(depot_id, fuel) + int(pair["lead_time"]))
        demand = sum(pair["forecast"][:k])
        have = float(st["inventory"].get(fuel, 0.0)) + self.inbound_total(station_id, fuel)
        return max(0.0, demand - have)

    def reserve(self, depot_id: str, fuel: str, station_id: str) -> tuple[float, list[tuple[str, float]]]:
        """Liters of this depot that `station_id` must leave for the depot's own other stations."""
        inv = max(0.0, self.depot_inventory(depot_id, fuel))
        own = self.own_stations.get(depot_id, [])
        needs = {s: self.need_until_resupply(s, fuel, depot_id) for s in own}
        others = [(s, n) for s, n in needs.items() if s != station_id and n > 0]
        others_total = sum(n for _, n in others)
        if station_id not in own:  # cross-region backup shipment: own stations come first
            return min(inv, others_total), others
        mine = needs.get(station_id, 0.0)
        total = others_total + mine
        if total <= 0 or others_total <= 0:
            return 0.0, others
        available = max(inv - others_total, inv * mine / total)
        return max(0.0, inv - available), others

    def project_with(self, pair: dict[str, Any], arrival_tick: int, qty: float) -> tuple[list[float], int | None]:
        inbound = self._inbound_map(pair)
        inbound[arrival_tick] = inbound.get(arrival_tick, 0.0) + qty
        st = self.snap.station_by_id[pair["station_id"]]
        proj = project(
            inventory=float(st["inventory"].get(pair["fuel"], 0.0)),
            capacity=float(st["capacity"][pair["fuel"]]),
            forecast=pair["forecast"],
            inbound=inbound,
            now=self.now,
        )
        return proj.levels, proj.ticks_to_stockout

    def _inbound_map(self, pair: dict[str, Any]) -> dict[int, float]:
        return dict(inbound_by_tick(self.snap.allocations, self.snap.route_by_id, pair["station_id"], pair["fuel"], self.now))

    # ------------------------------------------------------------ main

    def run(self) -> Plan:
        proposals: list[Proposal] = []
        at_risk_stations = set()
        candidates = []
        for st in self.snap.stations:
            if st.get("status") != "OPEN":
                self.alerts.append({
                    "id": f"outage:{st['id']}", "level": "warning", "kind": "outage", "station_id": st["id"],
                    "message": f"{_short(st)} is in OUTAGE: it serves nothing and cannot receive shipments.",
                })
                continue
            for fuel in FUELS:
                pair = self.pairs.get((st["id"], fuel))
                if pair is None:
                    continue
                if pair.get("ticks_to_stockout") == 0 and float(st["inventory"].get(fuel, 0)) < 1:
                    self.alerts.append({
                        "id": f"stockout:{st['id']}:{fuel}", "level": "critical", "kind": "stockout",
                        "station_id": st["id"], "fuel": fuel,
                        "message": f"{_short(st)} is out of {fuel.lower()}.",
                    })
                if self.is_candidate(pair):
                    at_risk_stations.add(st["id"])
                    if (st["id"], fuel) not in self.skip:
                        candidates.append(pair)

        self.route_alerts(at_risk_stations)
        candidates.sort(key=lambda p: (-p["risk"], -p["projected_unmet"], p["level_at_lead"] / max(1.0, p["capacity"])))
        for pair in candidates:
            proposal = self.plan_pair(pair)
            if proposal is not None:
                proposals.append(proposal)

        reserves = {}
        for depot_id, own in self.own_stations.items():
            for fuel in FUELS:
                reserves[(depot_id, fuel)] = round(
                    min(max(0.0, self.depot_inventory(depot_id, fuel)),
                        sum(self.need_until_resupply(s, fuel, depot_id) for s in own)), 1)
        return Plan(proposals=proposals, alerts=self.alerts, reserves=reserves, blocked=self.blocked)

    def is_candidate(self, pair: dict[str, Any]) -> bool:
        buffer_ticks = round(BUFFER_HOURS * self.tph)
        tts = pair.get("ticks_to_stockout")
        if tts is not None and tts <= int(pair["lead_time"]) + buffer_ticks:
            return True
        return float(pair["level_at_lead"]) < LOW_FILL * float(pair["capacity"])

    def route_alerts(self, at_risk: set[str]) -> None:
        for st in self.snap.stations:
            if st.get("status") != "OPEN":
                continue
            routes = self.snap.routes_to(st["id"])
            reasons = [self.usable(r) for r in routes]
            if routes and not any(ok for ok, _ in reasons):
                single = len(routes) == 1
                spof = " It has a single route: a single point of failure." if single else ""
                self.alerts.append({
                    "id": f"no_route:{st['id']}", "level": "critical" if st["id"] in at_risk else "warning",
                    "kind": "no_route", "station_id": st["id"],
                    "message": f"No route to {_short(st)}: {'; '.join(r for _, r in reasons if r)}.{spof}",
                })

    def plan_pair(self, pair: dict[str, Any]) -> Proposal | None:
        snap = self.snap
        st = snap.station_by_id[pair["station_id"]]
        fuel = pair["fuel"]
        cap = float(st["capacity"][fuel])
        inv = float(st["inventory"].get(fuel, 0.0))
        inbound = self.inbound_total(st["id"], fuel)
        target = TARGET_FILL * cap - inv - inbound
        headroom = cap - inv - inbound
        if target < MIN_SHIPMENT:
            return None

        routes = snap.routes_to(st["id"])
        primary = routes[0] if routes else None
        skipped: list[str] = []
        for route in routes:
            ok, why = self.usable(route)
            if not ok:
                skipped.append(why or route["id"])
                continue
            depot = snap.depot_by_id[route["source_depot_id"]]
            depot_inv = self.depot_inventory(depot["id"], fuel)
            reserve, reserved_for = self.reserve(depot["id"], fuel, st["id"])
            limits = [
                ("refill to 85%", target),
                ("station headroom", headroom),
                (f"route max {route['max_shipment']:,.0f} L", float(route["max_shipment"])),
                (f"{_short(depot)} depot stock", depot_inv),
                (f"{_short(depot)} dispatch left this tick", self.dispatch_left(depot["id"])),
            ]
            if reserve > 0:
                held = ", ".join(_short(snap.station_by_id[s]) for s, _ in reserved_for)
                limits.append((f"depot reserve of {reserve:,.0f} L held for {held}", depot_inv - reserve))
            qty = floor_to(min(v for _, v in limits))
            if qty < MIN_SHIPMENT:
                binding = min(limits, key=lambda x: x[1])[0]
                skipped.append(f"{route['id']} limited by {binding}")
                continue
            caps = [name for name, v in limits[1:] if v <= min(x[1] for x in limits) + ROUND_TO and name != "refill to 85%"]
            req = {
                "idempotency_key": "precheck",
                "source_depot_id": depot["id"],
                "destination_station_id": st["id"],
                "route_id": route["id"],
                "fuel_type": fuel,
                "quantity": qty,
            }
            rejection = precheck(req, snap, self.committed)
            if rejection is not None:
                PREVENTED.labels(rejection.code).inc()
                self.blocked.append((st["id"], fuel, rejection.code))
                skipped.append(f"{route['id']}: {rejection.code}")
                continue
            backup_reason = None
            if primary is not None and route["id"] != primary["id"]:
                backup_reason = skipped[0] if skipped else "primary route unavailable"
            proposal = self.build(pair, st, depot, route, qty, caps, backup_reason, routes)
            self.committed.add(req)
            return proposal
        if skipped and all("limited by" in s for s in skipped):
            self.alerts.append({
                "id": f"depot_low:{st['id']}:{fuel}", "level": "warning", "kind": "depot_low",
                "station_id": st["id"], "fuel": fuel,
                "message": f"{_short(st)} {fuel.lower()} is at risk but no depot can ship: {'; '.join(skipped)}.",
            })
        return None

    def build(
        self,
        pair: dict[str, Any],
        st: dict[str, Any],
        depot: dict[str, Any],
        route: dict[str, Any],
        qty: float,
        caps: list[str],
        backup_reason: str | None,
        routes: list[dict[str, Any]],
    ) -> Proposal:
        fuel = pair["fuel"]
        transit = int(route["transit_ticks"])
        arrival = self.now + transit
        levels_with, tts_after = self.project_with(pair, arrival, qty)
        lead = transit + 1
        risk_after = risk_score(tts_after, lead, self.horizon, self.snap.tick_minutes)
        tts = pair.get("ticks_to_stockout")
        cap = float(pair["capacity"])
        tph = self.tph
        rate = pair.get("forecast_next_hour", 0.0)

        if tts is not None:
            situation = (
                f"{_short(st)} {fuel.lower()} is projected to run out in {tts / tph:.1f} h (tick {self.now + tts}) "
                f"at about {rate:,.0f} L/h"
            )
        else:
            level = float(pair["level_at_lead"])
            situation = (
                f"{_short(st)} {fuel.lower()} is projected to fall to {level / cap:.0%} of capacity ({level:,.0f} L) "
                f"by the time a shipment can land"
            )
        if pair.get("spike_reason"):
            situation += f"; {pair['spike_reason']}"
        elif pair.get("upcoming_spike"):
            up = pair["upcoming_spike"]
            situation += f"; a x{up['multiplier']:.1f} demand spike is scheduled from tick {up['start_tick']}"
        action = (
            f"Send {qty:,.0f} L from {_short(depot)} via {route['id']} ({transit} ticks, {transit / tph:.1f} h), "
            f"arriving at tick {arrival}"
        )
        text = f"{situation}. {action}."
        if backup_reason:
            text += f" Backup route used because {backup_reason}."
        if caps:
            text += f" Quantity capped by {', '.join(caps)}."
        text += f" Risk {pair['risk']:.2f} -> {risk_after:.2f}."
        if self.fallback:
            text += " (Fallback forecast: prediction service unavailable.)"

        alternative = self.alternative(pair, st, route, qty, routes)
        what_if = [
            {"tick": self.now + k, "without": round(pair["levels"][k], 1), "with": round(levels_with[k], 1)}
            for k in range(min(WHAT_IF_TICKS, len(levels_with)))
        ]
        return Proposal(
            station_id=st["id"],
            station_name=_name(st),
            fuel=fuel,
            depot_id=depot["id"],
            depot_name=_name(depot),
            route_id=route["id"],
            transit_ticks=transit,
            quantity=qty,
            uses_backup_route=backup_reason is not None,
            backup_reason=backup_reason,
            caps=caps,
            reason=text,
            risk_before=float(pair["risk"]),
            risk_after=round(risk_after, 4),
            tts_before=tts,
            tts_after=tts_after,
            confidence=float(pair["confidence"]),
            fallback=self.fallback,
            alternative=alternative,
            what_if=what_if,
            facts={
                "station": _short(st), "fuel": fuel, "quantity_l": qty, "depot": _short(depot), "route": route["id"],
                "transit_hours": round(transit / tph, 2), "hours_to_stockout": None if tts is None else round(tts / tph, 2),
                "forecast_l_per_hour": round(rate, 1), "inventory_l": float(st["inventory"].get(fuel, 0)),
                "capacity_l": cap, "risk_before": pair["risk"], "risk_after": round(risk_after, 3),
                "spike": pair.get("spike_reason"), "backup_reason": backup_reason, "caps": caps,
                "confidence": pair["confidence"], "fallback": self.fallback,
            },
        )

    def alternative(
        self, pair: dict[str, Any], st: dict[str, Any], chosen: dict[str, Any], qty: float, routes: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        for r in routes:
            if r["id"] == chosen["id"] or not self.usable(r)[0]:
                continue
            depot = self.snap.depot_by_id[r["source_depot_id"]]
            alt_qty = floor_to(min(qty, float(r["max_shipment"]), self.depot_inventory(depot["id"], pair["fuel"])))
            if alt_qty >= MIN_SHIPMENT:
                delta = int(r["transit_ticks"]) - int(chosen["transit_ticks"])
                when = f"{abs(delta)} ticks {'later' if delta > 0 else 'sooner'}" if delta else "at the same time"
                return {
                    "kind": "backup_route", "route_id": r["id"], "depot_id": depot["id"], "quantity": alt_qty,
                    "description": f"Ship {alt_qty:,.0f} L from {_short(depot)} via {r['id']} instead; arrives {when}.",
                }
        shortfall = floor_to(float(pair.get("projected_unmet") or 0.0)) + ROUND_TO
        smaller = max(MIN_SHIPMENT, min(qty / 2, shortfall)) if shortfall < qty else floor_to(qty / 2)
        smaller = floor_to(smaller)
        if MIN_SHIPMENT <= smaller < qty:
            return {
                "kind": "smaller_quantity", "route_id": chosen["id"], "depot_id": chosen["source_depot_id"],
                "quantity": smaller,
                "description": f"Send only {smaller:,.0f} L now to cover the projected shortfall and keep depot stock "
                               f"for other stations; reassess next tick.",
            }
        return None


def plan(snap: Snapshot, analysis: dict[str, Any], *, skip_pairs: set[tuple[str, str]] | None = None) -> Plan:
    return Planner(snap, analysis, skip_pairs=skip_pairs).run()


def risk_label(value: float) -> str:
    return risk_level(value)
