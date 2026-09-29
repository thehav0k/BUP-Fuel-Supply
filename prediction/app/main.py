"""Stateless prediction service.

POST /forecast and POST /risk take the network snapshot and recent demand in the body and return calibrated
forecasts, spike flags, stockout projections, risk, confidence and depot projections. Nothing is stored.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI
from prometheus_client import Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, ConfigDict, Field

import fuelcore

VERSION = "1.0.0"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "component": "prediction",
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, default=str)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
log = logging.getLogger("prediction")

ANALYZE_SECONDS = Histogram(
    "prediction_analyze_seconds", "Time spent computing forecasts and risk", ["endpoint"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
FORECAST_MAPE = Gauge("prediction_forecast_mape", "Mean absolute percentage error of the calibrated forecast", ["fuel"])
CALIBRATION_RATIO = Gauge("prediction_calibration_ratio", "Calibration ratio actual/baseline", ["station", "fuel"])


class AnalyzeRequest(BaseModel):
    """Mirrors the simulator's JSON; unknown fields are kept and ignored."""

    model_config = ConfigDict(extra="allow")

    tick: int
    sim_time: str
    tick_minutes: float = 15
    horizon: int = Field(default=48, ge=1, le=192)
    regions: list[dict[str, Any]] = []
    stations: list[dict[str, Any]] = []
    depots: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    allocations: list[dict[str, Any]] = []
    supply_arrivals: list[dict[str, Any]] = []
    demand: list[dict[str, Any]] = []


app = FastAPI(title="Fuel prediction service", version=VERSION)
Instrumentator(excluded_handlers=["/metrics", "/health"]).instrument(app).expose(app, include_in_schema=False)


def _run(req: AnalyzeRequest, endpoint: str) -> dict[str, Any]:
    started = time.perf_counter()
    result = fuelcore.analyze(req.model_dump(), calibrate_enabled=True)
    elapsed = time.perf_counter() - started
    ANALYZE_SECONDS.labels(endpoint).observe(elapsed)

    by_fuel: dict[str, list[float]] = defaultdict(list)
    for p in result["pairs"]:
        CALIBRATION_RATIO.labels(p["station_id"], p["fuel"]).set(p["ratio"])
        if p["mape"] is not None:
            by_fuel[p["fuel"]].append(p["mape"])
    for fuel, values in by_fuel.items():
        FORECAST_MAPE.labels(fuel).set(sum(values) / len(values))
    log.info("analyzed", extra={"fields": {"tick": req.tick, "endpoint": endpoint, "ms": round(elapsed * 1000, 2)}})
    return result


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "prediction", "version": VERSION, "model": "calibrated-baseline"}


@app.post("/forecast")
def forecast(req: AnalyzeRequest) -> dict[str, Any]:
    """Forecast series, calibration ratio, spike flags and confidence per station-fuel."""
    result = _run(req, "forecast")
    keep = (
        "station_id", "fuel", "ratio", "mape", "confidence", "calibration_points", "spike", "spike_reason",
        "upcoming_spike", "multiplier_now", "forecast", "baseline", "forecast_next_hour",
    )
    return {
        "model": result["model"],
        "tick": result["tick"],
        "horizon": result["horizon"],
        "pairs": [{k: p[k] for k in keep} for p in result["pairs"]],
    }


@app.post("/risk")
def risk(req: AnalyzeRequest) -> dict[str, Any]:
    """Everything in /forecast plus stockout projection, risk score and depot projections."""
    return _run(req, "risk")
