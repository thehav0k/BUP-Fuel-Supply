from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

REQUEST = {
    "tick": 8,
    "sim_time": "2026-01-01T02:00:00",
    "tick_minutes": 15,
    "regions": [{"id": "region-chattogram", "demand_factor": 1.08}],
    "stations": [{
        "id": "station-coxsbazar", "region_id": "region-chattogram", "status": "OPEN", "demand_profile": "regional",
        "demand_multiplier": 1.0, "capacity": {"DIESEL": 12000, "PETROL": 12000, "OCTANE": 7000},
        "inventory": {"DIESEL": 7500, "PETROL": 400, "OCTANE": 4200},
    }],
    "depots": [{"id": "depot-patiya", "inventory": {"DIESEL": 55000, "PETROL": 42000, "OCTANE": 24000}}],
    "routes": [{"id": "route-patiya-coxsbazar", "source_depot_id": "depot-patiya",
                "destination_station_id": "station-coxsbazar", "transit_ticks": 3, "max_shipment": 6000,
                "status": "AVAILABLE"}],
    "events": [],
    "allocations": [],
    "supply_arrivals": [],
    "demand": [
        {"station_id": "station-coxsbazar", "fuel_type": "PETROL", "tick": t, "demand_liters": 60.0}
        for t in range(0, 8)
    ],
    "unknown_field": "ignored",
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_risk_returns_all_pairs_and_depots():
    r = client.post("/risk", json=REQUEST)
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "calibrated-baseline"
    assert {p["fuel"] for p in body["pairs"]} == {"DIESEL", "PETROL", "OCTANE"}
    petrol = next(p for p in body["pairs"] if p["fuel"] == "PETROL")
    # 7600/96 * 0.65 * 1.08 = 55.6 L/tick at night; observed 60 -> ratio ~1.08
    assert 1.0 < petrol["ratio"] < 1.2
    assert petrol["lead_time"] == 4
    assert petrol["ticks_to_stockout"] is not None and petrol["risk_level"] == "high"
    assert len(body["depots"]) == 3


def test_forecast_is_subset_without_projection():
    body = client.post("/forecast", json=REQUEST).json()
    pair = body["pairs"][0]
    assert "forecast" in pair and "levels" not in pair and "risk" not in pair


def test_metrics_exposed():
    client.post("/risk", json=REQUEST)
    text = client.get("/metrics").text
    assert "prediction_analyze_seconds" in text
    assert 'prediction_forecast_mape{fuel="PETROL"}' in text


def test_bad_request_is_422():
    assert client.post("/risk", json={"tick": "x"}).status_code == 422
