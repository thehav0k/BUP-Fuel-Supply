# Fuel Supply Operations Platform

A decision-support platform for a fuel distribution network. It monitors the BUP Fuel Supply Simulator, forecasts
demand at every station, detects stockout risk, and recommends shipments from depots to stations with a plain-language
reason. Recommendations are submitted after operator approval or automatically.

## Results

Measured against the official simulator image (`asifmahmoud414/bup-fuel-supply-simulator:1.0.0`), same seed, same world.

| Scenario (192 ticks = 2 simulated days) | Service level | Unmet demand | Rejected shipments |
|---|---|---|---|
| No action | 42.7% | 115,061 L | n/a |
| **This platform, auto mode** | **100%** | **0 L** | **0** |

The scenario includes three crises: a ×1.8 demand spike in Dhaka, a Gazipur → Mirpur route disruption and a 50%
supply shortfall at Patiya depot.

- **Resilience:** 27 of 27 live checks pass (crises, all five fault types, a stopped prediction service, a stopped
  database, simulator reset).
- **Load:** a p95 API latency of 37 ms at 50 concurrent users, against a 300 ms target.

---

## Contents

1. [Features](#1-features)
2. [Quick start](#2-quick-start)
3. [Architecture](#3-architecture)
4. [Key concepts](#4-key-concepts)
5. [How a decision is made](#5-how-a-decision-is-made)
6. [Components](#6-components)
7. [Algorithms and techniques](#7-algorithms-and-techniques)
8. [Resilience](#8-resilience)
9. [Simulator behaviour accounted for](#9-simulator-behaviour-accounted-for)
10. [Design decisions](#10-design-decisions)
11. [Configuration](#11-configuration)
12. [Project structure](#12-project-structure)
13. [Testing](#13-testing)

---

## 1. Features

- **Demand forecasting.** All 12 station-fuel pairs are forecast over a 12-hour horizon, calibrated against observed
  demand. Scheduled demand spikes are included before they start.
- **Stockout risk.** Each pair gets its time to stockout and a 0–1 risk score, measured against shipment lead time.
- **Shipment recommendations.** Each one carries quantity, route, depot, risk before and after, confidence, an
  alternative and a what-if projection. Every recommendation is explained in plain language.
- **Zero-rejection submission.** Every shipment is pre-checked against the simulator's rules in the simulator's own
  validation order before it is sent.
- **Three operating modes.**
  - Manual: operator approval for every shipment.
  - Auto: fully automatic.
  - Hybrid: automatic for low-risk, high-confidence cases only.
- **Crisis handling.** Demand spikes, route disruptions (with backup routing), station outages, depot constraints,
  shipment delays and supply shortfalls.
- **Fault tolerance.** Retries, a circuit breaker, a last-known-good state, a forecast fallback and a database outage
  buffer.
- **Operator dashboard.**
  - Network view on a map of Bangladesh.
  - Recommendation queue.
  - Decision log.
  - System health.
  - Scenario controls.
- **Observability.** Prometheus metrics, a provisioned Grafana dashboard and structured JSON logs.

---

## 2. Quick start

Requirements: Docker (with Compose) and Python 3.

```bash
./run.sh              # build and start all services, wait until healthy, print URLs
./run.sh demo         # start, reset the simulator and start its clock
./run.sh verify       # run the 27 live crisis, fault and fallback checks
./run.sh compare      # no-action vs platform on the same scenario
./run.sh e2e 200      # auto mode for 200 ticks, assert service level and zero rejections
./run.sh loadtest     # k6 load test: 50 virtual users, 1 minute
./run.sh logs         # follow backend logs
./run.sh stop         # stop services (data kept)
./run.sh down         # stop and remove services and data
```

| Service | URL |
|---|---|
| Operator dashboard | <http://localhost:3000> (port set by `FRONTEND_PORT`) |
| Backend API (OpenAPI) | <http://localhost:8001/docs> |
| Backend health | <http://localhost:8001/health> |
| Grafana (admin / admin) | <http://localhost:3001> |
| Prometheus | <http://localhost:9090> |
| Simulator console | <http://localhost:8000/admin> |

On first run, `run.sh` creates `.env` from `.env.example`. The simulator starts paused at `SIMULATION_SPEED=1`.

---

## 3. Architecture

```text
                         ┌──────────────────────────┐
                         │  Frontend :3000          │  React dashboard, served by nginx;
                         │                          │  polls the backend every 2 s
                         └────────────┬─────────────┘
                                      │ /api
┌──────────────────┐    writes   ┌────▼─────────────────────┐   /risk    ┌──────────────────────┐
│ Postgres :5432   │◄────────────┤  Backend :8001           ├───────────►│ Prediction :8002     │
│ decision log,    │             │  sync loop, SSE listener,│            │ calibrated forecast  │
│ recommendations, │             │  decision engine,        │            │ and risk (stateless) │
│ demand history   │             │  approvals, API          │            └──────────────────────┘
└──────────────────┘             └────┬─────────────────────┘                      ▲
                                      │ REST poll + SSE trigger             ┌──────┴───────────────┐
                                      │ POST /v1/allocations                │ Prometheus :9090     │
                                 ┌────▼─────────────────────┐               │ Grafana :3001        │
                                 │  Simulator :8000         │               └──────────────────────┘
                                 │  (official image)        │
                                 └──────────────────────────┘
```

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, httpx, httpx-sse, tenacity, SQLAlchemy (async) |
| Prediction | Python 3.12, FastAPI |
| Shared math | `shared/fuelcore`, a pure-Python package used by both services |
| Frontend | React, TypeScript, Vite, Tailwind CSS, TanStack Query, Recharts, nginx |
| Storage | PostgreSQL 16 |
| Observability | Prometheus, Grafana, JSON logs |
| Delivery | Docker Compose, GitHub Actions |

**Principles**

- **A single point of contact with the simulator.** Only the backend calls it, so retries, caching and fault
  handling live in one place.
- **REST is the source of truth.** Server-Sent Events only trigger an early re-fetch.
- **A separate prediction service**, so it can fail on its own. The backend then runs the same formulas without
  calibration (shared package), so a forecast is always available.
- **Reads come from memory.** The dashboard API answers from the backend's in-memory state and never waits on the
  simulator or the database.
- **Postgres is write-behind.** A database outage never blocks the API or the decision engine.

---

## 4. Key concepts

| Term | Meaning |
|---|---|
| Tick | One simulation step (15 simulated minutes by default). Ticks per day = `1440 / tick_minutes` |
| Station | A fuel station: Mirpur and Tongi in Dhaka; Karnaphuli and Cox's Bazar in Chattogram |
| Depot | A supply store: Gazipur in Dhaka, Patiya in Chattogram. Both are resupplied on a fixed schedule |
| Route | Depot → station link with a transit time and a maximum load. Two are cross-region backups |
| Allocation | A shipment. It is the only write the platform makes to the simulator |
| Service level | served ÷ (served + unmet) liters; the metric being optimised |
| Inbound | Fuel already dispatched to a station (PENDING or IN_TRANSIT) |
| Lead time | Route transit time + 1 tick: how long a shipment ordered now takes to help |
| Headroom | Capacity − inventory − inbound |
| Event | A crisis in the simulated world (demand spike, route disruption, outage, shortfall and others) |
| Fault | An injected API failure (latency, unavailable, error rate, stale data, stream disconnect) |

---

## 5. How a decision is made

Once per simulation tick:

```text
 1. SYNC        fetch the full network state (stations, depots, routes, shipments, events, metrics)
 2. FORECAST    demand for the next 48 ticks, for all 12 station-fuel pairs
 3. RISK        project each tank forward; find the first tick it cannot meet demand
 4. PLAN        select candidates, size shipments, choose routes, respect depot reserves
 5. VALIDATE    pre-check each shipment against every simulator rule
 6. RECOMMEND   publish a recommendation with its reason, risk before/after and alternative
 7. DECIDE      operator approval (manual) or automatic submission (auto / hybrid)
 8. SUBMIT      POST /v1/allocations with an idempotency key; track PENDING → IN_TRANSIT → ARRIVED
```

### Worked example: Mirpur diesel during a demand spike

It is 08:00 (a peak hour). Mirpur holds 1,500 L of diesel in a 15,000 L tank, and a ×1.8 Dhaka demand spike is
active.

| Step | Calculation | Result |
|---|---|---|
| Forecast | 8,500 L/day ÷ 96 ticks × 1.45 (peak) × 1.0 (region) × 1.8 (spike) | 231 L per tick |
| Time to stockout | 1,500 L ÷ 231 L per tick | 6 ticks (1.5 h) |
| Lead time | Gazipur → Mirpur transit 2 ticks + 1 | 3 ticks |
| Risk | (3 + 24 − 6) ÷ 24 | 0.88 (high) |
| Candidate? | 6 ≤ lead time + 2 h (3 + 8 = 11) | yes |
| Quantity | min(85% refill = 11,250 L, route max 7,000 L, depot stock, dispatch left) | 7,000 L |
| Validation | depot, station and route status; capacities; inventory; dispatch; tank room | pass |

The recommendation reads: *"Mirpur diesel is projected to run out in 1.5 h (tick 38) at about 925 L/h; demand
multiplier ×1.80. Send 7,000 L from Gazipur via route-gazipur-mirpur (2 ticks, 0.5 h), arriving at tick 34. Quantity
capped by route max 7,000 L. Risk 0.88 → 0.00."*

On approval, the backend re-fetches state, re-validates, and submits with the key
`32-station-mirpur-DIESEL-route-gazipur-mirpur-0`.

---

## 6. Components

### 6.1 Sync (`backend/app/runtime.py`)

- Every 2 s, all resources are fetched concurrently. A simulator SSE event triggers an immediate re-fetch.
- A snapshot replaces the previous one only when every resource arrived ("last known good"). Otherwise the previous
  state is served and marked degraded.
- Demand history: 2,000 rows on startup, then 200 per cycle, merged by row id and persisted.
- Simulator resets are detected when the tick goes backwards, allocation ids shrink, or a reset notice arrives. The
  platform then clears its in-memory state and open recommendations.

### 6.2 Forecast (`shared/fuelcore/forecast.py`, `prediction/app/main.py`)

```text
baseline per tick = daily liters (profile, fuel) ÷ ticks per day
                    × hour-of-day factor × region demand factor × station demand multiplier
```

- **Calibration:** actual ÷ baseline over the last 16 ticks, clamped to 0.5–3.0.
- **Confidence:** 1 − MAPE over the same window (typically about 0.9).
- **Spike flag:** raised when the multiplier is above 1.0, or when actual demand exceeds 1.3× the baseline for 4
  consecutive ticks.
- **Scheduled spikes:** the multiplier for any past or future tick is rebuilt from the event list.
- **Fallback:** if the prediction service does not answer within 1 s, the backend runs the same model uncalibrated
  and flags its recommendations as fallback.

### 6.3 Risk (`shared/fuelcore/projection.py`)

- A 48-tick projection per pair adds scheduled arrivals (clipped at tank capacity) and subtracts forecast demand. The
  first shortfall gives the time to stockout.
- Risk is 1.0 when a shipment ordered now cannot arrive in time, and 0.0 with at least 6 hours of slack. It is linear
  in between. Levels: high ≥ 0.7, medium ≥ 0.4.

### 6.4 Decision engine (`backend/app/engine.py`)

1. **Candidates:** stockout within lead time + 2 h, or projected level under 35% of capacity at arrival. Stations in
   outage are excluded.
2. **Priority:** highest risk first, then the most projected unmet liters.
3. **Quantity:** refill toward 85% of capacity, capped by tank headroom, route maximum, depot stock after reserve,
   and depot dispatch capacity left this tick. Shipments under 500 L are skipped.
4. **Routing:** the fastest usable route. The cross-region backup is used, and stated in the reason, when the primary
   route is disrupted, about to be disrupted, or its depot is short. Single-route stations raise a "no route" alert.
5. **Depot reserve:** a depot retains what its own stations need until its next delivery. Under scarcity, those
   stations share stock in proportion to need.

### 6.5 Validation (`backend/app/validation.py`)

Checks run in the simulator's own order, plus two stricter platform rules:

| # | Rule | Code |
|---|---|---|
| 1 | Idempotency key unused | IDEMPOTENCY_KEY_MISMATCH |
| 2 | Depot, station and route exist | NOT_FOUND |
| 3 | Route connects that depot and station | ROUTE_MISMATCH |
| 4 | Depot OPEN or CONSTRAINED | DEPOT_CLOSED |
| 5 | Station OPEN | STATION_CLOSED |
| 6 | Route AVAILABLE | ROUTE_DISRUPTED |
| 7 | Quantity ≤ route maximum | ROUTE_CAPACITY_EXCEEDED |
| 8 | Depot has the fuel | INSUFFICIENT_INVENTORY |
| 9 | Depot dispatch capacity not exceeded this tick | DISPATCH_CAPACITY_EXCEEDED |
| 10 | Station tank has room | DESTINATION_CAPACITY_EXCEEDED |
| + | No route disruption starting at departure | ROUTE_DISRUPTION_SCHEDULED |
| + | Inventory + inbound + quantity within capacity | DESTINATION_OVERFLOW_RISK |

### 6.6 Recommendations and approvals (`backend/app/recommendations.py`)

```text
            ┌──────────► REJECTED   (operator)
            ├──────────► EXPIRED    (no action within 4 ticks)
            ├──────────► SUPERSEDED (no longer valid against current state)
 OPEN ──────┼──────────► FAILED     (validation or simulator refusal; code recorded)
            │
            └─ approve / auto ─► SUBMITTING ─► SUBMITTED ─► PENDING → IN_TRANSIT → ARRIVED
                                     │
                                     └─ 503 or timeout: replayed with the same idempotency key
```

- **Modes:**
  - `manual` (default): every shipment waits for an operator.
  - `auto`: every shipment is submitted automatically.
  - `hybrid`: shipments that are not high risk, have confidence ≥ 0.8 and don't use the fallback forecast are submitted automatically.
- **Approval re-validates** against freshly fetched state. The quantity is reduced to fit when conditions have changed.
- **A 409 is recorded and never retried** blindly. A new recommendation with a new key follows if the need remains.
- **Automatic submission is paused** while data is stale or the circuit breaker is open.
- **Decision log:** every decision is recorded with its action, actor, tick, allocation id, live allocation status
  and any failure reason.

### 6.7 Dashboard (`frontend/src`)

| View | Content |
|---|---|
| Network | KPIs; per-station fuel levels, hours to stockout, risk and spike indicators; depots with the next delivery; routes; a map of Bangladesh with every depot, station and route at its real location; per-station forecast chart |
| Recommendations | Reason, quantity, route, risk before and after, confidence, alternative, what-if chart, approve and reject |
| History and events | Decision log with live allocation status, allocations (cancel if PENDING), crisis events |
| System health | Simulator (circuit breaker), database, prediction service, SSE stream, decision engine |
| Scenario control | Run, pause, step, reset; inject any event or fault |

Degraded, stale-data and fallback banners stay visible whenever they are active.

### 6.8 Observability

- **Metrics:** simulator call rate, errors and latency; breaker state; SSE status; decision cycle time;
  recommendation outcomes; 409s by code; service level; stale and fallback flags; forecast error per fuel.
- **Grafana:** a provisioned dashboard at `observability/grafana/dashboards/fuel-ops.json`.
- **Logs:** structured JSON lines with `tick`, `component` and `event` fields.

---

## 7. Algorithms and techniques

### Data acquisition

| Part | Technique | Implementation | Code |
|---|---|---|---|
| Sync loop | Polling with event-triggered refresh | 2 s poll; SSE events wake the loop early; nothing depends on SSE | `backend/app/runtime.py` |
| Fetching | Concurrent fan-out (`asyncio.gather`) | All resources requested in parallel, so one sync costs one round trip | `runtime.py` |
| Consistency | All-or-nothing snapshot swap (last known good) | State is replaced only on a complete fetch; the engine never plans on partial data | `runtime.py`, `state.py` |
| Transient errors | Retry with exponential backoff and jitter (tenacity) | Up to 3 attempts per GET on 503, timeout or connection errors, plus a second pass for resources that failed | `backend/app/sim/client.py` |
| Outages | Circuit breaker (closed → open → half-open) | Opens after 5 consecutive failures; one trial call after 10 s | `backend/app/sim/breaker.py` |
| Live stream | SSE consumer with exponential-backoff reconnect | 1 s to 30 s backoff; a full re-fetch on every reconnect (no replay) | `backend/app/sim/sse.py` |
| Error handling | Normalisation into typed exceptions | `{"error":{}}`, `{"detail":{}}` and `{"detail":[...]}` map to unavailable, conflict, not found or validation | `backend/app/sim/errors.py` |
| Reset detection | Monotonic-counter invariant | Tick and allocation id must not decrease; reset notices also trigger it | `runtime.py` |

### Forecasting and risk

| Part | Technique | Implementation | Code |
|---|---|---|---|
| Demand forecast | Multiplicative baseline with daily seasonality | Profile × hour-of-day factor × region factor × station multiplier | `shared/fuelcore/forecast.py` |
| Scheduled spikes | Event-timeline reconstruction | Multiplier for any tick derived from demand-spike events | `forecast.py` |
| Calibration | Sliding-window ratio adjustment, clamped | Actual ÷ baseline over 16 ticks, bounded 0.5–3.0 | `forecast.py`, `prediction/app/main.py` |
| Confidence | 1 − MAPE | Forecast error over the calibration window | `forecast.py` |
| Spike detection | Threshold with run-length rule | Multiplier > 1, or > 1.3× baseline for 4 consecutive ticks | `forecast.py` |
| Stockout projection | Discrete-time inventory simulation | 48-tick walk with arrivals clipped at capacity | `shared/fuelcore/projection.py` |
| Risk score | Piecewise-linear function of slack | (lead time + 6 h − time to stockout) ÷ 6 h, clamped to 0–1 | `projection.py` |
| Depot outlook | Cumulative scheduled arrivals | Stock plus deliveries within the horizon; the next delivery tick | `shared/fuelcore/analyze.py` |
| Forecast fallback | Graceful degradation on a shared code path | The same model runs uncalibrated when the service misses its 1 s timeout | `backend/app/forecaster.py` |

### Planning and execution

| Part | Technique | Implementation | Code |
|---|---|---|---|
| Prioritisation | Greedy priority ordering | Sorted by risk, then projected unmet liters | `backend/app/engine.py` |
| Shipment sizing | Minimum over capacity constraints | min(85% refill, headroom, route max, depot stock after reserve, dispatch left) | `engine.py` |
| Intra-tick budgets | Running resource accounting | Depot stock, dispatch capacity and inbound are updated as shipments are planned and submitted | `engine.py`, `validation.py` |
| Route selection | Shortest feasible alternative | Routes ordered by transit time; the first usable one with enough supply | `engine.py` |
| Scarce supply | Proportional fair share | max(stock − others' need, stock × own need ÷ total need) | `engine.py` |
| Pre-validation | Ordered rule chain | Mirrors the simulator's validation order, plus two safety rules | `backend/app/validation.py` |
| What-if preview | Re-projection with a hypothetical shipment | The projection re-run with the shipment at its arrival tick | `engine.py` |
| Explanations | Template generation from computed values; optional LLM rewrite | Cerebras rewrite with a 1.5 s timeout in the background; the template is kept on failure | `engine.py`, `backend/app/explain.py` |
| Duplicate protection | Deterministic idempotency keys | `{tick}-{station}-{fuel}-{route}-{n}`; safe replay after timeouts | `engine.py` |
| Lifecycle | Finite state machine with expiry | Expiry after 4 ticks; re-validation every tick | `backend/app/recommendations.py` |
| Automation | Policy gate | Mode, risk, confidence, fallback, stale-data and breaker conditions | `recommendations.py` |

### Storage, presentation and monitoring

| Part | Technique | Implementation | Code |
|---|---|---|---|
| Persistence | Write-behind queue with retry | An async producer/consumer; ordered writes with backoff while the database is down | `backend/app/persistence.py` |
| Writes | Idempotent upserts (`INSERT … ON CONFLICT`) | Safe to retry | `persistence.py` |
| API | In-memory read model | Served from memory; p95 37 ms at 50 concurrent users | `backend/app/views.py` |
| Dashboard data | Polling with a stale-while-revalidate cache (TanStack Query) | 2 s refresh; last data kept on error | `frontend/src/api/` |
| Map | Equirectangular projection with cos(latitude) correction; Douglas–Peucker simplification | Official division boundaries (geoBoundaries, CC BY 4.0); markers of nearby sites spread out, with leader lines to their true positions | `scripts/gen_bangladesh_map.py`, `frontend/src/components/network/NetworkMap.tsx` |
| Metrics | Prometheus counters, gauges and histograms | p95 via `histogram_quantile` | `backend/app/metrics.py` |
| Logging | Structured JSON | `tick`, `component` and `event` fields | `backend/app/logs.py` |

---

## 8. Resilience

| Condition | Detection | Behaviour |
|---|---|---|
| Latency | Call exceeds the 2 s timeout | Counted as a failure; retried; visible in latency metrics |
| Simulator unavailable | 503 `FAULT_INJECTED` | Retries with backoff; the circuit breaker opens after 5 consecutive failures; last known good state served with a degraded flag; automatic submission paused; automatic recovery |
| Intermittent errors | Random 503s | Retries and per-resource re-fetch keep data current |
| Stale data | `X-Simulator-Stale: true` | Stale flag shown; automatic submission paused |
| Stream disconnect | 503 on `/v1/stream` | Reconnect with backoff; polling keeps data current |
| Prediction service down | No response within 1 s | Uncalibrated baseline in the backend; recommendations flagged as fallback |
| Database down | Connection error | Service continues from memory; writes queued and replayed |
| Simulator reset | Tick regression or reset notice | In-memory state and open recommendations cleared |

---

## 9. Simulator behaviour accounted for

Verified against the live simulator:

- **Overflow is discarded.** Fuel beyond tank capacity is lost on arrival, so shipments are sized against capacity − inventory − inbound.
- **Same-tick disruptions fail shipments.** An allocation created in the tick a route disruption starts ends as FAILED, and its fuel is not refunded. Such routes are treated as unusable.
- **Departure is immediate.** Allocations depart in their creation tick and arrive `transit_ticks` later. Depot stock is deducted at creation.
- **Dispatch capacity is per tick.** It counts only allocations created in the current tick.
- **The no-action baseline declines steadily.** Service level is 1.00 at tick 48, 0.88 at tick 96, 0.46 at tick 192 and 0.18 at tick 480.

---

## 10. Design decisions

- **A formula-based forecast instead of machine learning.** Demand follows documented profiles and hour-of-day
  factors. A calibrated baseline reaches about 90% confidence, explains itself in one sentence, and has no training or
  drift to manage.
- **Pre-validation instead of error handling.** Replicating the simulator's rule order means requests that would be
  rejected are never sent.
- **SSE as a trigger only.** The stream has no replay, so REST remains authoritative and polling continues without it.
- **Idempotent replay.** Timeouts are retried with the same key. A request that was already accepted is returned,
  not duplicated.
- **Automatic and hybrid modes.** At normal speed a simulated day passes in about 12 seconds, too fast for manual
  approval. Hybrid keeps high-risk decisions with an operator.
- **Proportional sharing under scarcity.** When a depot cannot cover every station until its next delivery, supply is
  divided by need, so stock never sits idle while another station runs dry.

---

## 11. Configuration

Set in `.env` (created from `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `SIMULATION_SPEED` | `1` | Simulator ticks per second while running |
| `TICK_MINUTES` | `15` | Simulated minutes per tick |
| `SIMULATOR_START_MODE` | `paused` | `paused` or `running` |
| `DEFAULT_MODE` | `manual` | Initial approval mode: `manual`, `auto` or `hybrid` |
| `FRONTEND_PORT` | `3000` | Host port for the dashboard |
| `LLM_EXPLANATIONS` | `false` | Enable LLM-written explanations |
| `CEREBRAS_API_KEY` | empty | API key for LLM explanations |

---

## 12. Project structure

```text
run.sh                          single entry point (start, verify, compare, load test)
docker-compose.yml              all services
shared/fuelcore/                forecast, projection and risk (used by backend and prediction)
prediction/app/main.py          prediction service: POST /forecast, POST /risk, /metrics
backend/app/
  runtime.py                    sync loop, SSE handling, reset detection, decision cycle
  sim/client.py                 simulator client: timeouts, retries, breaker, stale header
  sim/breaker.py                circuit breaker
  sim/sse.py                    SSE listener with reconnect
  sim/errors.py                 error-shape parsing
  forecaster.py                 prediction client with local fallback
  engine.py                     decision engine
  validation.py                 pre-validation in simulator order
  recommendations.py            recommendation lifecycle, approvals, automation, decision log
  persistence.py                write-behind Postgres persistence
  explain.py                    optional LLM explanations
  api.py, views.py              dashboard API
frontend/src/                   React dashboard
observability/                  Prometheus configuration, Grafana dashboard
scripts/verify_live.py          live crisis, fault and fallback verification
scripts/compare.py              no-action vs platform comparison
scripts/e2e.py                  end-to-end run in auto mode
scripts/gen_bangladesh_map.py   map data generation from official boundaries
loadtest/k6.js                  load test
.github/workflows/ci.yml        lint, tests, build, compose smoke test
```

---

## 13. Testing

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e 'shared[dev]' -e 'backend[dev]' -e 'prediction[dev]'
(cd shared && pytest -q) && (cd backend && pytest -q) && (cd prediction && pytest -q)
./run.sh verify && ./run.sh compare && ./run.sh e2e 200 && ./run.sh loadtest
```

### Unit tests: 65 passing

- `shared/` (34): forecast model, hour factors, calibration, spike detection, projection, risk.
- `backend/` (26):
  - one test per simulator rejection code;
  - error-shape parsing and idempotency keys;
  - engine rules: backup routing, no-route alert, dispatch limits within a tick;
  - retries, circuit breaker, stale header and SSE parsing, against a mocked HTTP layer.
- `prediction/` (5): API and metrics.

### Live verification (`scripts/verify_live.py`): 27 of 27 passing

Each check injects the condition into the running simulator or stops a real container, then asserts on the platform's
API.

| Area | Injected | Verified |
|---|---|---|
| Crisis | Demand spike ×1.8 (Dhaka) | Stations flagged; recommendations issued; approval creates a shipment that departs |
| Crisis | Route disruption (Gazipur → Mirpur) | Backup route used; nothing proposed on the disrupted route |
| Crisis | Route disruption (Gazipur → Tongi) | "No route" alert for a single-route station |
| Crisis | Supply shortfall ×0.5 (Gazipur) | Future arrivals halved; depot reserve adjusted |
| Crisis | Station outage (Cox's Bazar) | Outage shown and alerted; no shipments proposed |
| Crisis | All of the above | Zero rejections by the simulator |
| Fault | `unavailable` | Degraded state with last known good data; breaker opens; automatic submission held; recovery |
| Fault | `latency` 2.5 s | Treated as failure; recovery |
| Fault | `error_rate` 25% | Data age ≤ 3.1 s; never degraded |
| Fault | `stale_data` | Stale flag; automatic submission paused; cleared afterwards |
| Fault | `stream_disconnect` | SSE down while polling keeps data current; reconnect afterwards |
| Fallback | Prediction service stopped | Baseline fallback; recommendations flagged; calibrated forecasts resume |
| Fallback | Database stopped | API (2 ms) and engine continue; queued writes flushed on recovery |
| Reset | `/admin/reset` | Detected; state and open recommendations cleared |

### End-to-end

`scripts/e2e.py`, 200 ticks in auto mode: service level 1.000, 0 L unmet, 0 failed shipments, 0 rejections.

### Load test (`loadtest/k6.js`: 50 virtual users, 1 minute, `/api/state` and `/api/recommendations`)

| Requests | Throughput | Errors | Median | p95 | p99 | Target |
|---|---|---|---|---|---|---|
| 167,072 | 2,784 req/s | 0.00% | 15.9 ms | 37.2 ms | 45.3 ms | p95 < 300 ms |
