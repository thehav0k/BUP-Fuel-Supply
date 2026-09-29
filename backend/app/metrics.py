from prometheus_client import Counter, Gauge, Histogram

SIM_REQUESTS = Counter("sim_requests_total", "Simulator calls by endpoint and result", ["endpoint", "result"])
SIM_LATENCY = Histogram(
    "sim_request_seconds", "Simulator call latency", ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0),
)
BREAKER_STATE = Gauge("sim_circuit_breaker_state", "Circuit breaker: 0 closed, 1 half-open, 2 open")
SIM_STALE = Gauge("sim_stale", "1 while the simulator reports X-Simulator-Stale")
SIM_TICK = Gauge("sim_tick", "Current simulation tick")
DEGRADED = Gauge("platform_degraded", "1 while serving last good state because sync is failing")
DATA_AGE = Gauge("platform_data_age_seconds", "Age of the last good state")

SSE_CONNECTED = Gauge("sse_connected", "1 while the SSE stream is connected")
SSE_EVENTS = Counter("sse_events_total", "SSE events received", ["event"])
SSE_RECONNECTS = Counter("sse_reconnects_total", "SSE reconnect attempts")

CYCLE_SECONDS = Histogram(
    "decision_cycle_seconds", "Duration of one decision cycle (forecast + plan + auto submit)",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
RECOMMENDATIONS = Counter("recommendations_total", "Recommendation outcomes", ["outcome"])
ALLOCATION_409 = Counter("allocation_conflicts_total", "409 responses from POST /v1/allocations by code", ["code"])
ALLOCATIONS_SUBMITTED = Counter("allocations_submitted_total", "Allocation submissions by result", ["result"])
PREVENTED = Counter("allocation_prechecks_blocked_total", "Requests we did not send because a pre-check failed", ["code"])

SERVICE_LEVEL = Gauge("sim_service_level", "service_level from /v1/metrics")
UNMET_LITERS = Gauge("sim_unmet_demand_liters", "unmet_demand_liters from /v1/metrics")
ALLOCATION_FAILURES = Gauge("sim_allocation_failures", "allocation_failures from /v1/metrics")
STATION_RISK = Gauge("station_risk", "Stockout risk 0..1", ["station", "fuel"])

FALLBACK_ACTIVE = Gauge("prediction_fallback_active", "1 while using the backend baseline fallback")
PREDICTION_REQUESTS = Counter("prediction_requests_total", "Calls to the prediction service", ["result"])

DB_UP = Gauge("db_up", "1 when the database is reachable")
DB_PENDING = Gauge("db_pending_writes", "Queued database writes")
