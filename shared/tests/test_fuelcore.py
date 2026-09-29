from datetime import datetime

import pytest

from fuelcore import (
    MultiplierTimeline,
    analyze,
    baseline_series,
    calibrate,
    hour_factor,
    inbound_by_tick,
    parse_sim_time,
    project,
    risk_level,
    risk_score,
    ticks_per_day,
)

MIRPUR = {
    "id": "station-mirpur",
    "region_id": "region-dhaka",
    "status": "OPEN",
    "demand_profile": "urban_high",
    "demand_multiplier": 1.0,
    "capacity": {"DIESEL": 15000, "PETROL": 14000, "OCTANE": 9000},
    "inventory": {"DIESEL": 9000, "PETROL": 9000, "OCTANE": 5000},
}
ROUTES = [
    {"id": "route-gazipur-mirpur", "source_depot_id": "depot-gazipur", "destination_station_id": "station-mirpur",
     "transit_ticks": 2, "max_shipment": 7000, "status": "AVAILABLE"},
    {"id": "route-patiya-mirpur", "source_depot_id": "depot-patiya", "destination_station_id": "station-mirpur",
     "transit_ticks": 4, "max_shipment": 5000, "status": "AVAILABLE"},
]


def spike(status="ACTIVE", start=10, end=20, mult=1.8, regions=("region-dhaka",), stations=()):
    return {"id": 1, "type": "demand_spike", "start_tick": start, "end_tick": end, "status": status,
            "parameters": {"region_ids": list(regions), "station_ids": list(stations), "multiplier": mult}}


def test_ticks_per_day_is_derived_from_tick_minutes():
    assert ticks_per_day(15) == 96
    assert ticks_per_day(30) == 48
    assert ticks_per_day(10) == 144


@pytest.mark.parametrize(
    ("profile", "hour", "expected"),
    [
        ("urban_high", 6, 0.70), ("urban_high", 7, 1.45), ("urban_high", 9, 1.45), ("urban_high", 10, 0.70),
        ("urban_high", 20, 1.45), ("urban_high", 21, 0.70),
        ("industrial", 5, 0.45), ("industrial", 6, 1.55), ("industrial", 17, 1.55), ("industrial", 18, 0.45),
        ("highway", 6, 1.35), ("highway", 12, 0.75), ("highway", 16, 1.35),
        ("regional", 6, 0.65), ("regional", 7, 1.25), ("regional", 20, 1.25), ("regional", 21, 0.65),
        ("unknown", 12, 1.0),
    ],
)
def test_hour_factor_boundaries(profile, hour, expected):
    assert hour_factor(profile, hour) == expected


def test_parse_sim_time_accepts_naive_and_offset():
    assert parse_sim_time("2026-01-01T03:15:00") == datetime(2026, 1, 1, 3, 15)
    assert parse_sim_time("2026-01-01T03:15:00+00:00") == datetime(2026, 1, 1, 3, 15)


def test_baseline_formula_matches_guide():
    tl = MultiplierTimeline(MIRPUR, [])
    # 00:00, off-peak: 8500 / 96 * 0.70 * 1.0 * 1.0
    [b] = baseline_series(profile="urban_high", fuel="DIESEL", region_factor=1.0, timeline=tl, ticks=[0],
                          base_time=datetime(2026, 1, 1), base_tick=0, tick_minutes=15)
    assert b == pytest.approx(8500 / 96 * 0.70)
    # 30-minute ticks halve the per-tick liters: never hard-code 96
    [b30] = baseline_series(profile="urban_high", fuel="DIESEL", region_factor=1.08, timeline=tl, ticks=[0],
                            base_time=datetime(2026, 1, 1), base_tick=0, tick_minutes=30)
    assert b30 == pytest.approx(8500 / 48 * 0.70 * 1.08)


def test_multiplier_timeline_rebuilds_history_and_future():
    st = dict(MIRPUR, demand_multiplier=1.8)
    tl = MultiplierTimeline(st, [spike(status="ACTIVE", start=10, end=20)])
    assert tl.base == pytest.approx(1.0)
    assert tl.at(9) == pytest.approx(1.0)
    assert tl.at(10) == pytest.approx(1.8)
    assert tl.at(19) == pytest.approx(1.8)
    assert tl.at(20) == pytest.approx(1.0)


def test_scheduled_spike_is_forecast_before_it_starts():
    tl = MultiplierTimeline(MIRPUR, [spike(status="SCHEDULED", start=30, end=40, mult=2.0)])
    assert tl.at(29) == 1.0 and tl.at(30) == 2.0
    assert tl.upcoming(25, 48) == {"start_tick": 30, "end_tick": 40, "multiplier": 2.0}
    assert tl.upcoming(25, 4) is None


def test_spike_filters_are_intersected():
    other = dict(MIRPUR, id="station-tongi")
    ev = spike(stations=("station-mirpur",))
    assert MultiplierTimeline(MIRPUR, [ev]).spikes
    assert not MultiplierTimeline(other, [ev]).spikes
    assert not MultiplierTimeline(dict(MIRPUR, region_id="region-chattogram"), [spike()]).spikes


def test_calibration_ratio_is_clamped_and_needs_points():
    assert calibrate([100] * 16, [50] * 16).ratio == pytest.approx(2.0)
    assert calibrate([1000] * 16, [50] * 16).ratio == 3.0
    assert calibrate([10] * 16, [50] * 16).ratio == 0.5
    assert calibrate([100] * 3, [50] * 3).ratio == 1.0  # too few points
    assert calibrate([100] * 16, [50] * 16, enabled=False).ratio == 1.0


def test_calibration_uses_last_16_ticks_only():
    actual = [500] * 10 + [100] * 16
    base = [100] * 26
    assert calibrate(actual, base).ratio == pytest.approx(1.0)


def test_confidence_from_mape():
    cal = calibrate([90, 110] * 8, [100] * 16)
    assert cal.ratio == pytest.approx(1.0)
    assert cal.mape == pytest.approx((10 / 90 + 10 / 110) / 2)
    assert cal.confidence == pytest.approx(1 - cal.mape)


def test_spike_by_ratio_requires_four_consecutive_ticks():
    assert calibrate([100] * 12 + [140] * 4, [100] * 16).spike_by_ratio
    assert not calibrate([100] * 13 + [140] * 3, [100] * 16).spike_by_ratio
    assert not calibrate([100] * 12 + [140, 140, 120, 140], [100] * 16).spike_by_ratio


def test_projection_counts_inbound_and_clips_overflow():
    p = project(inventory=100, capacity=1000, forecast=[60, 60, 60], inbound={}, now=0)
    assert p.levels == [40, 0, 0]
    assert p.ticks_to_stockout == 1
    assert p.unmet == pytest.approx(20 + 60)

    p = project(inventory=100, capacity=1000, forecast=[60, 60, 60], inbound={1: 500}, now=0)
    assert p.ticks_to_stockout is None
    assert p.levels == [40, 480, 420]

    p = project(inventory=900, capacity=1000, forecast=[10, 10], inbound={0: 500}, now=0)
    assert p.levels == [990, 980]  # overflow above capacity is lost


def test_inbound_uses_eta_or_created_plus_transit():
    allocs = [
        {"status": "IN_TRANSIT", "destination_station_id": "station-mirpur", "fuel_type": "DIESEL", "quantity": 3000,
         "expected_arrival_tick": 12, "created_tick": 10, "route_id": "route-gazipur-mirpur"},
        {"status": "PENDING", "destination_station_id": "station-mirpur", "fuel_type": "DIESEL", "quantity": 1000,
         "expected_arrival_tick": None, "created_tick": 11, "route_id": "route-patiya-mirpur"},
        {"status": "ARRIVED", "destination_station_id": "station-mirpur", "fuel_type": "DIESEL", "quantity": 999,
         "expected_arrival_tick": 5, "created_tick": 3, "route_id": "route-gazipur-mirpur"},
        {"status": "IN_TRANSIT", "destination_station_id": "station-mirpur", "fuel_type": "PETROL", "quantity": 999,
         "expected_arrival_tick": 12, "created_tick": 10, "route_id": "route-gazipur-mirpur"},
    ]
    routes = {r["id"]: r for r in ROUTES}
    assert inbound_by_tick(allocs, routes, "station-mirpur", "DIESEL", now=11) == {12: 3000, 15: 1000}


def test_risk_score_against_lead_time():
    # 15-minute ticks: 6 h window = 24 ticks
    assert risk_score(2, lead_time=3, horizon=48, tick_minutes=15) == 1.0
    assert risk_score(3, lead_time=3, horizon=48, tick_minutes=15) == 1.0
    assert risk_score(15, lead_time=3, horizon=48, tick_minutes=15) == pytest.approx(0.5)
    assert risk_score(27, lead_time=3, horizon=48, tick_minutes=15) == 0.0
    assert risk_score(None, lead_time=3, horizon=48, tick_minutes=15) == 0.0
    assert risk_level(0.8) == "high" and risk_level(0.5) == "medium" and risk_level(0.1) == "low"


def _request(**over):
    req = {
        "tick": 40,
        "sim_time": "2026-01-01T10:00:00",
        "tick_minutes": 15,
        "horizon": 48,
        "regions": [{"id": "region-dhaka", "demand_factor": 1.0}],
        "stations": [MIRPUR],
        "depots": [{"id": "depot-gazipur", "inventory": {"DIESEL": 60000, "PETROL": 45000, "OCTANE": 26000}}],
        "routes": ROUTES,
        "events": [],
        "allocations": [],
        "supply_arrivals": [
            {"id": "s1", "depot_id": "depot-gazipur", "fuel_type": "DIESEL", "quantity": 12000,
             "planned_tick": 64, "status": "SCHEDULED"},
            {"id": "s0", "depot_id": "depot-gazipur", "fuel_type": "DIESEL", "quantity": 18000,
             "planned_tick": 12, "status": "ARRIVED"},
        ],
        "demand": [],
    }
    req.update(over)
    return req


def test_analyze_calibrates_to_observed_demand():
    # Observed demand is exactly 2x the baseline for the last 16 ticks.
    tl = MultiplierTimeline(MIRPUR, [])
    ticks = list(range(24, 40))
    base = baseline_series(profile="urban_high", fuel="DIESEL", region_factor=1.0, timeline=tl, ticks=ticks,
                           base_time=datetime(2026, 1, 1, 10), base_tick=40, tick_minutes=15)
    demand = [{"station_id": "station-mirpur", "fuel_type": "DIESEL", "tick": t, "demand_liters": 2 * b}
              for t, b in zip(ticks, base, strict=True)]
    out = analyze(_request(demand=demand))
    pair = next(p for p in out["pairs"] if p["fuel"] == "DIESEL")
    assert pair["ratio"] == pytest.approx(2.0)
    assert pair["confidence"] == pytest.approx(1.0)
    assert pair["forecast"][0] == pytest.approx(2 * pair["baseline"][0], rel=1e-3)
    assert pair["lead_time"] == 3
    assert len(pair["forecast"]) == 48 and len(pair["levels"]) == 48

    fallback = analyze(_request(demand=demand), calibrate_enabled=False)
    fpair = next(p for p in fallback["pairs"] if p["fuel"] == "DIESEL")
    assert fallback["model"] == "baseline" and fpair["ratio"] == 1.0


def test_analyze_flags_spike_and_depot_next_arrival():
    st = dict(MIRPUR, demand_multiplier=1.8)
    out = analyze(_request(stations=[st], events=[spike(status="ACTIVE", start=30, end=60)]))
    assert all(p["spike"] for p in out["pairs"])
    depot = next(d for d in out["depots"] if d["fuel"] == "DIESEL")
    assert depot["next_arrival"] == {"tick": 64, "quantity": 12000.0, "status": "SCHEDULED", "in_hours": 6.0}
    assert depot["levels"][23] == 60000 and depot["levels"][24] == 72000


def test_low_inventory_is_high_risk():
    st = dict(MIRPUR, inventory={"DIESEL": 100, "PETROL": 9000, "OCTANE": 5000})
    out = analyze(_request(stations=[st]))
    diesel = next(p for p in out["pairs"] if p["fuel"] == "DIESEL")
    assert diesel["ticks_to_stockout"] == 0
    assert diesel["risk"] == 1.0 and diesel["risk_level"] == "high"
