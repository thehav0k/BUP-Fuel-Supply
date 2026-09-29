import copy
import json

import httpx
import pytest
import respx

from app.engine import make_key, plan
from app.sim.breaker import CircuitBreaker
from app.sim.client import SimulatorClient
from app.sim.errors import CircuitOpen, SimConflict, SimUnavailable, parse_error_body
from app.state import Snapshot
from app.validation import precheck
from fuelcore import analyze

BASE = "http://sim"

WORLD = {
    "instance": {"tick": 10, "sim_time": "2026-01-01T02:30:00", "tick_minutes": 15, "status": "PAUSED"},
    "regions": [{"id": "region-dhaka", "demand_factor": 1.0}, {"id": "region-chattogram", "demand_factor": 1.08}],
    "depots": [
        {"id": "depot-gazipur", "name": "Gazipur Depot", "region_id": "region-dhaka", "status": "OPEN",
         "dispatch_capacity_per_tick": 12000, "capacity": {"DIESEL": 90000, "PETROL": 70000, "OCTANE": 45000},
         "inventory": {"DIESEL": 60000, "PETROL": 45000, "OCTANE": 26000}},
        {"id": "depot-patiya", "name": "Patiya Depot", "region_id": "region-chattogram", "status": "OPEN",
         "dispatch_capacity_per_tick": 11000, "capacity": {"DIESEL": 85000, "PETROL": 65000, "OCTANE": 40000},
         "inventory": {"DIESEL": 55000, "PETROL": 42000, "OCTANE": 24000}},
    ],
    "stations": [
        {"id": "station-mirpur", "name": "Mirpur Fuel Station", "region_id": "region-dhaka", "status": "OPEN",
         "demand_profile": "urban_high", "demand_multiplier": 1.0,
         "capacity": {"DIESEL": 15000, "PETROL": 14000, "OCTANE": 9000},
         "inventory": {"DIESEL": 1500, "PETROL": 9000, "OCTANE": 5000}},
        {"id": "station-tongi", "name": "Tongi Industrial Station", "region_id": "region-dhaka", "status": "OPEN",
         "demand_profile": "industrial", "demand_multiplier": 1.0,
         "capacity": {"DIESEL": 18000, "PETROL": 9000, "OCTANE": 6000},
         "inventory": {"DIESEL": 11000, "PETROL": 6000, "OCTANE": 3500}},
    ],
    "routes": [
        {"id": "route-gazipur-mirpur", "source_depot_id": "depot-gazipur", "destination_station_id": "station-mirpur",
         "transit_ticks": 2, "max_shipment": 7000, "status": "AVAILABLE"},
        {"id": "route-patiya-mirpur", "source_depot_id": "depot-patiya", "destination_station_id": "station-mirpur",
         "transit_ticks": 4, "max_shipment": 5000, "status": "AVAILABLE"},
        {"id": "route-gazipur-tongi", "source_depot_id": "depot-gazipur", "destination_station_id": "station-tongi",
         "transit_ticks": 2, "max_shipment": 6500, "status": "AVAILABLE"},
    ],
    "supply_arrivals": [],
    "events": [],
    "allocations": [],
    "metrics": {"service_level": 1.0},
}


def snap(**over):
    w = copy.deepcopy(WORLD)
    w.update(over)
    return Snapshot(**w)


def req(**over):
    r = {"idempotency_key": "k-1", "source_depot_id": "depot-gazipur", "destination_station_id": "station-mirpur",
         "route_id": "route-gazipur-mirpur", "fuel_type": "DIESEL", "quantity": 3000}
    r.update(over)
    return r


def mutate(fn):
    s = snap()
    fn(s)
    return s


# ---------------------------------------------------------------- one test per simulator rejection code

def test_ok_request_passes():
    assert precheck(req(), snap()) is None


@pytest.mark.parametrize(
    ("request_over", "state", "code"),
    [
        ({"idempotency_key": "used"}, None, "IDEMPOTENCY_KEY_MISMATCH"),
        ({"source_depot_id": "depot-x"}, None, "NOT_FOUND"),
        ({"route_id": "route-gazipur-tongi"}, None, "ROUTE_MISMATCH"),
        ({}, lambda s: s.depot_by_id["depot-gazipur"].update(status="CLOSED"), "DEPOT_CLOSED"),
        ({}, lambda s: s.station_by_id["station-mirpur"].update(status="OUTAGE"), "STATION_CLOSED"),
        ({}, lambda s: s.route_by_id["route-gazipur-mirpur"].update(status="DISRUPTED"), "ROUTE_DISRUPTED"),
        ({"quantity": 7001}, None, "ROUTE_CAPACITY_EXCEEDED"),
        ({}, lambda s: s.depot_by_id["depot-gazipur"]["inventory"].update(DIESEL=2999), "INSUFFICIENT_INVENTORY"),
        ({}, lambda s: s.allocations.append({"id": 1, "idempotency_key": "x", "source_depot_id": "depot-gazipur",
                                             "destination_station_id": "station-tongi", "fuel_type": "PETROL",
                                             "quantity": 10000, "created_tick": 10, "status": "PENDING",
                                             "route_id": "route-gazipur-tongi"}), "DISPATCH_CAPACITY_EXCEEDED"),
        ({"quantity": 5000},
         lambda s: s.station_by_id["station-mirpur"]["inventory"].update(DIESEL=11000),
         "DESTINATION_CAPACITY_EXCEEDED"),
    ],
)
def test_precheck_catches_every_code(request_over, state, code):
    s = mutate(state) if state else snap()
    rejection = precheck(req(**request_over), s, used_keys={"used"})
    assert rejection is not None and rejection.code == code


def test_dispatch_counts_only_this_tick():
    s = snap(allocations=[{"id": 1, "idempotency_key": "x", "source_depot_id": "depot-gazipur", "quantity": 11000,
                           "created_tick": 9, "status": "IN_TRANSIT", "destination_station_id": "station-tongi",
                           "fuel_type": "PETROL", "route_id": "route-gazipur-tongi", "expected_arrival_tick": 11}])
    assert precheck(req(), s, strict=False) is None


def test_strict_rules_block_scheduled_disruption_and_overflow():
    s = snap(events=[{"id": 1, "type": "route_disruption", "start_tick": 10, "end_tick": 12, "status": "SCHEDULED",
                      "parameters": {"route_ids": ["route-gazipur-mirpur"]}}])
    assert precheck(req(), s).code == "ROUTE_DISRUPTION_SCHEDULED"
    s = snap(allocations=[{"id": 1, "idempotency_key": "x", "source_depot_id": "depot-patiya", "quantity": 10000,
                           "created_tick": 8, "status": "IN_TRANSIT", "destination_station_id": "station-mirpur",
                           "fuel_type": "DIESEL", "route_id": "route-patiya-mirpur", "expected_arrival_tick": 12}])
    assert precheck(req(quantity=5000), s).code == "DESTINATION_OVERFLOW_RISK"


# ---------------------------------------------------------------- engine

def _analysis(s):
    data = {k: getattr(s, k) for k in ("regions", "stations", "depots", "routes", "events", "allocations",
                                       "supply_arrivals")}
    return analyze({"tick": s.tick, "sim_time": s.sim_time, "tick_minutes": 15, **data}, calibrate_enabled=False)


def test_engine_proposes_valid_refill_for_low_station():
    s = snap()
    result = plan(s, _analysis(s))
    mirpur = [p for p in result.proposals if p.station_id == "station-mirpur" and p.fuel == "DIESEL"]
    assert mirpur and mirpur[0].route_id == "route-gazipur-mirpur"
    assert 500 <= mirpur[0].quantity <= 7000
    assert "run out" in mirpur[0].reason or "capacity" in mirpur[0].reason
    for p in result.proposals:  # every proposal passes the simulator's rules
        assert precheck(p.request("fresh-key"), s, strict=False) is None


def test_engine_uses_backup_when_primary_disrupted():
    s = mutate(lambda s: s.route_by_id["route-gazipur-mirpur"].update(status="DISRUPTED"))
    p = next(p for p in plan(s, _analysis(s)).proposals if p.station_id == "station-mirpur")
    assert p.route_id == "route-patiya-mirpur" and p.uses_backup_route
    assert p.quantity <= 5000 and "Backup route" in p.reason


def test_engine_raises_no_route_alert():
    s = mutate(lambda s: s.route_by_id["route-gazipur-tongi"].update(status="DISRUPTED"))
    alerts = plan(s, _analysis(s)).alerts
    assert any(a["kind"] == "no_route" and a["station_id"] == "station-tongi" for a in alerts)


def test_engine_respects_dispatch_capacity_across_proposals():
    s = mutate(lambda s: [st["inventory"].update(DIESEL=500, PETROL=500, OCTANE=300) for st in s.stations])
    result = plan(s, _analysis(s))
    from_gazipur = sum(p.quantity for p in result.proposals if p.depot_id == "depot-gazipur")
    assert from_gazipur <= 12000


def test_idempotency_key_is_deterministic_and_never_reused():
    used = set()
    k1 = make_key(5, "station-mirpur", "DIESEL", "route-gazipur-mirpur", used)
    assert k1 == "5-station-mirpur-DIESEL-route-gazipur-mirpur-0"
    used.add(k1)
    assert make_key(5, "station-mirpur", "DIESEL", "route-gazipur-mirpur", used).endswith("-1")


# ---------------------------------------------------------------- error parsing

def test_parse_both_error_shapes():
    assert parse_error_body({"error": {"code": "FAULT_INJECTED", "message": "x"}}) == ("FAULT_INJECTED", "x")
    assert parse_error_body({"detail": {"code": "ROUTE_DISRUPTED", "message": "y"}}) == ("ROUTE_DISRUPTED", "y")
    code, msg = parse_error_body({"detail": [{"loc": ["body", "quantity"], "msg": "must be > 0"}]})
    assert code == "VALIDATION_ERROR" and "quantity" in msg
    assert parse_error_body(b"not json", 502)[0] == "HTTP_502"


# ---------------------------------------------------------------- client: retries, breaker, stale

def client(**kw):
    return SimulatorClient(BASE, backoff_initial=0.001, backoff_max=0.002, **kw)


@respx.mock
async def test_get_retries_503_then_succeeds_and_reads_stale_header():
    route = respx.get(f"{BASE}/v1/instance").mock(side_effect=[
        httpx.Response(503, json={"error": {"code": "FAULT_INJECTED", "message": "down"}}),
        httpx.Response(200, json={"tick": 3}, headers={"x-simulator-stale": "true"}),
    ])
    resp = await client().get("/v1/instance")
    assert route.call_count == 2 and resp.data == {"tick": 3} and resp.stale


@respx.mock
async def test_breaker_opens_after_five_failures_and_half_opens():
    now = [0.0]
    breaker = CircuitBreaker(5, 10.0, clock=lambda: now[0])
    c = client(breaker=breaker, get_attempts=1)
    route = respx.get(f"{BASE}/v1/instance").mock(return_value=httpx.Response(503, json={"error": {"code": "X"}}))
    for _ in range(5):
        with pytest.raises(SimUnavailable):
            await c.get("/v1/instance")
    with pytest.raises(CircuitOpen):
        await c.get("/v1/instance")
    assert route.call_count == 5
    now[0] = 11.0
    route.mock(return_value=httpx.Response(200, json={"tick": 1}))
    assert (await c.get("/v1/instance")).data == {"tick": 1}
    assert breaker.state == "closed"


@respx.mock
async def test_post_replays_same_key_on_503_and_accepts_200():
    route = respx.post(f"{BASE}/v1/allocations").mock(side_effect=[
        httpx.Response(503, json={"error": {"code": "FAULT_INJECTED"}}),
        httpx.Response(200, json={"id": 7, "status": "PENDING"}),
    ])
    resp = await client().create_allocation(req())
    assert resp.data["id"] == 7
    bodies = [call.request.content for call in route.calls]
    assert bodies[0] == bodies[1]


@respx.mock
async def test_409_is_not_retried():
    route = respx.post(f"{BASE}/v1/allocations").mock(
        return_value=httpx.Response(409, json={"detail": {"code": "ROUTE_DISRUPTED", "message": "no"}}))
    with pytest.raises(SimConflict) as exc:
        await client().create_allocation(req())
    assert exc.value.code == "ROUTE_DISRUPTED" and route.call_count == 1


@respx.mock
async def test_sse_parsing_dispatches_events():
    from app.sim.sse import CONNECTED, SSEListener

    body = (": connected\n\nevent: simulation.tick\ndata: {\"tick\": 4, \"sim_time\": \"x\"}\n\n"
            ": keepalive\n\nevent: simulator.notice\ndata: {\"message\": \"Simulation reset\"}\n\n")
    respx.get(f"{BASE}/v1/stream").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}))
    seen = []

    async def handler(name, data):
        seen.append((name, data))

    listener = SSEListener(BASE, handler)
    async with httpx.AsyncClient(base_url=BASE) as http:
        await listener.consume(http)
    assert seen == [(CONNECTED, None), ("simulation.tick", {"tick": 4, "sim_time": "x"}),
                    ("simulator.notice", {"message": "Simulation reset"})]


@respx.mock
async def test_sse_503_detail_shape_raises():
    from app.sim.sse import SSEListener

    respx.get(f"{BASE}/v1/stream").mock(return_value=httpx.Response(503, json={"detail": {"code": "FAULT_INJECTED"}}))

    async def handler(name, data):
        pass

    async with httpx.AsyncClient(base_url=BASE) as http:
        with pytest.raises(SimUnavailable):
            await SSEListener(BASE, handler).consume(http)


# ---------------------------------------------------------------- regression: batch auto-submit within one tick

@respx.mock
async def test_auto_batch_never_exceeds_depot_dispatch_capacity():
    """Found live: two auto submissions from one depot in one tick got DISPATCH_CAPACITY_EXCEEDED (409)."""
    from app.config import Settings
    from app.persistence import Persistence
    from app.recommendations import Recommendation, RecommendationService
    from app.state import StateStore

    posted = []

    def create(request):
        body = json.loads(request.content)
        posted.append(body)
        return httpx.Response(201, json={"id": len(posted), "status": "PENDING", **body})

    respx.post(f"{BASE}/v1/allocations").mock(side_effect=create)
    s = mutate(lambda s: s.station_by_id["station-tongi"]["inventory"].update(DIESEL=1000))
    svc = RecommendationService(Settings(default_mode="auto"), client(), StateStore(), Persistence(""))

    def rec(i, station, route, qty):
        return Recommendation(
            id=f"rec-{i}", created_tick=10, created_at="", expires_tick=14, status="OPEN", station_id=station,
            station_name=station, fuel="DIESEL", quantity=qty, route_id=route, depot_id="depot-gazipur",
            depot_name="Gazipur", transit_ticks=2, uses_backup_route=False, reason="", reason_source="template",
            risk_before=0.9 - i / 10, risk_after=0.1, ticks_to_stockout_before=3, ticks_to_stockout_after=None,
            confidence=0.9, fallback=False, caps=[], alternative=None, what_if=[], auto_eligible=True,
            idempotency_key=f"10-k-{i}")

    svc.recs = {"rec-1": rec(1, "station-mirpur", "route-gazipur-mirpur", 7000),
                "rec-2": rec(2, "station-tongi", "route-gazipur-tongi", 6500)}
    await svc.submit_auto(s)
    assert sum(p["quantity"] for p in posted) <= 12000
    assert [p["quantity"] for p in posted] == [7000, 5000]  # second one resized to the dispatch left
