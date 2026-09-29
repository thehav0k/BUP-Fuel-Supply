# Fuel Supply Operations Platform

**In one sentence:** a system that watches a simulated fuel network, predicts which petrol stations will run dry,
and ships fuel to them from depots in time, with a human able to approve every shipment.

**The result, measured on this machine against the official simulator image:** with the same world and the same three
crises (Dhaka demand spike, Gazipur → Mirpur road cut, Patiya supply cut), doing nothing ends at **42.7%** service level
after 192 ticks (2 days) with 115,061 L unmet. **Our platform ends at 100%**, with 0 L unmet, 0 failed shipments and
0 rejected shipments.

---

## Contents

1. [Quick start](#1-quick-start)
2. [Words you need to know](#2-words-you-need-to-know)
3. [The big picture](#3-the-big-picture)
4. [The life of one tick (worked example)](#4-the-life-of-one-tick-worked-example)
5. [Each part in detail](#5-each-part-in-detail)
6. [What happens when things break](#6-what-happens-when-things-break)
7. [Things we discovered about the simulator](#7-things-we-discovered-about-the-simulator)
8. [Demo script](#8-demo-script)
9. [Questions judges may ask](#9-questions-judges-may-ask)
10. [Where the code lives](#10-where-the-code-lives)
11. [Tests and results](#11-tests-and-results)

---

## 1. Quick start

You need Docker Desktop and Python 3.

```bash
./run.sh              # build and start everything, wait until healthy, print the links
./run.sh demo         # same, then reset the simulator and start its clock
./run.sh e2e 200      # same, then prove it works: auto mode for 200 ticks, check the service level
./run.sh compare      # "do nothing" vs "our platform" on the same world and the same crises
./run.sh verify       # inject every crisis, fault and fallback live and check the reaction (27 checks)
./run.sh loadtest     # k6: 50 users for 1 minute
./run.sh logs         # watch the backend's decisions live
./run.sh stop         # stop (keeps data)      ./run.sh down   # stop and delete everything
```

| Open this | To see |
|---|---|
| <http://localhost:3000> | The operator dashboard (5 tabs). **On the demo laptop it is <http://localhost:3002>** because another app uses 3000 |
| <http://localhost:8001/docs> | Every backend API endpoint, clickable |
| <http://localhost:8001/health> | Health of every component as JSON |
| <http://localhost:3001> | Grafana charts (login admin / admin, dashboard "Fuel Supply Operations") |
| <http://localhost:9090> | Prometheus, the metrics store behind Grafana |
| <http://localhost:8000/admin> | The simulator's own console |

The simulator starts **paused**, at a slow speed (`SIMULATION_SPEED=1` in `.env`), so a live audience can follow.

If the dashboard container is not built, serve it directly: `cd frontend && npm run build && npx vite preview --port 3002`.

---

## 2. Words you need to know

| Word | Meaning |
|---|---|
| **Simulator** | The official program that plays the "world". We are not allowed to change it. It runs at http://localhost:8000 |
| **Tick** | One step of simulated time, 15 minutes by default. 96 ticks = 1 simulated day. We always compute ticks per day as `1440 / tick_minutes`, never hard-code 96 |
| **Station** | A petrol station that sells fuel to customers. There are 4: Mirpur, Tongi (Dhaka region), Karnaphuli, Cox's Bazar (Chattogram region) |
| **Depot** | A big fuel store that supplies stations. There are 2: Gazipur (Dhaka) and Patiya (Chattogram). Depots get resupplied on a fixed schedule |
| **Fuel** | 3 types: DIESEL, PETROL, OCTANE. So there are 4 × 3 = **12 station-fuel pairs** to watch |
| **Route** | A road from a depot to a station, with a travel time (`transit_ticks`) and a max load (`max_shipment`). There are 6. Two are cross-region **backups** (Gazipur → Karnaphuli, Patiya → Mirpur) |
| **Allocation** | A shipment: "send X liters of fuel F from depot D to station S on route R". This is the **only** thing we are allowed to create in the simulator |
| **Service level** | served liters ÷ (served + unmet liters). 1.0 = no customer went without fuel. **This is the score we optimise** |
| **Stockout** | A station running out of a fuel. Customers who arrive get nothing, and that counts as "unmet" |
| **Inbound** | Fuel already on its way to a station (shipments that are PENDING or IN_TRANSIT) |
| **Lead time** | How long until a shipment ordered now can help: route travel time + 1 tick of safety |
| **Headroom** | Free space in a station's tank: capacity − inventory − inbound |
| **409** | The simulator's "rejected" answer, e.g. `ROUTE_DISRUPTED`, `INSUFFICIENT_INVENTORY`. We aim for zero of them |
| **Idempotency key** | A unique name for each shipment request. If the network drops and we resend the same request with the same key, the simulator returns the original instead of creating a duplicate |
| **Event** | A crisis injected into the world: demand spike, route disruption, station outage, depot constraint, shipment delay, supply shortfall |
| **Fault** | An injected IT failure: slow responses (`latency`), simulator down (`unavailable`), random errors (`error_rate`), old data (`stale_data`), live-update stream down (`stream_disconnect`) |
| **REST** | Normal request/response calls (`GET /v1/stations`). **This is our source of truth** |
| **SSE** | Server-Sent Events: a live stream where the simulator says "something changed". We only use it as a hint to re-fetch via REST |

---

## 3. The big picture

```text
                         ┌──────────────────────────┐
                         │  Frontend :3000          │  React dashboard. Asks the backend
                         │  (the operator's screen) │  for fresh data every 2 seconds
                         └────────────┬─────────────┘
                                      │ /api
┌──────────────────┐    writes   ┌────▼─────────────────────┐   /risk    ┌──────────────────────┐
│ Postgres :5432   │◄────────────┤  Backend :8001           ├───────────►│ Prediction :8002     │
│ decision log,    │             │  (the brain)             │            │ calibrated forecast  │
│ recommendations, │             │  sync loop, SSE listener,│            │ + risk (stateless)   │
│ demand history   │             │  decision engine,        │            └──────────────────────┘
└──────────────────┘             │  approvals, API          │                      ▲
                                 └────┬─────────────────────┘                      │ scrapes
                                      │ REST poll + SSE hint                ┌──────┴───────────────┐
                                      │ POST /v1/allocations                │ Prometheus :9090     │
                                 ┌────▼─────────────────────┐               │ + Grafana :3001      │
                                 │  Simulator :8000         │               │ (charts & metrics)   │
                                 │  (the world, untouched)  │               └──────────────────────┘
                                 └──────────────────────────┘
```

### Why it is shaped like this

- **Only the backend talks to the simulator.** Retries, caching and failure handling live in one place, not scattered.
- **The prediction service is separate** so we can switch it off during the demo and show the backend falling back
  to a simpler forecast. Both use the same math package (`shared/fuelcore`), so the fallback is the same formula, just
  without the calibration step.
- **Postgres is written in the background.** If the database dies, the platform keeps running from memory and saves
  later.
- **The dashboard only reads from the backend's memory**, so it answers instantly and never goes blank, even when
  the simulator is down.

---

## 4. The life of one tick (worked example)

Every time the simulator's clock moves one tick, this happens:

```text
 1. SYNC        fetch the whole world (stations, depots, routes, shipments, events, metrics)
 2. FORECAST    predict demand for the next 48 ticks, for all 12 station-fuel pairs
 3. RISK        project each tank's level forward; when does it hit zero?
 4. PLAN        pick who needs fuel, how much, from where, on which route
 5. CHECK       pre-check each shipment against every simulator rule
 6. RECOMMEND   create a recommendation card with a reason in plain words
 7. DECIDE      the operator clicks Approve (manual) or the system submits it (auto)
 8. SUBMIT      POST /v1/allocations, then track it: PENDING → IN_TRANSIT → ARRIVED
```

### Worked example: Mirpur diesel during a demand spike

Situation: it is 08:00 (a busy hour), Mirpur has 1,500 L of diesel in a 15,000 L tank, and a Dhaka demand spike of
×1.8 is active.

1. **Forecast.** Mirpur's profile is `urban_high`: 8,500 L of diesel per day.
   Per tick = 8,500 ÷ 96 ticks × 1.45 (busy hour) × 1.0 (Dhaka region) × 1.8 (spike) ≈ **231 L per tick**.
2. **Risk.** 1,500 L ÷ 231 L/tick ≈ empty in **6 ticks (1.5 hours)**.
   A shipment on the Gazipur → Mirpur route takes 2 ticks, so lead time = 2 + 1 = **3 ticks**.
   Risk score = (lead time + 24 − ticks to stockout) ÷ 24 = (3 + 24 − 6) ÷ 24 ≈ **0.88 (high)**.
3. **Plan.** Is it a candidate? Stockout (6) ≤ lead time + 2 hours (3 + 8 = 11). Yes.
   How much? Fill to 85%: 0.85 × 15,000 − 1,500 − 0 inbound = 11,250 L. The route can carry at most 7,000 L,
   so **7,000 L**. Gazipur has plenty and can dispatch 12,000 L this tick, so no other limit applies.
4. **Check.** Depot open? Station open? Route available? No disruption starting now? 7,000 ≤ route max?
   Depot has the fuel? Dispatch capacity left? Room in the tank? All pass.
5. **Recommend.** The card says, in plain words:
   *"Mirpur diesel is projected to run out in 1.5 h (tick 38) at about 925 L/h; demand multiplier ×1.80.
   Send 7,000 L from Gazipur via route-gazipur-mirpur (2 ticks, 0.5 h), arriving at tick 34.
   Quantity capped by route max 7,000 L. Risk 0.88 → 0.00."*
   It also shows an alternative (the Patiya backup route) and a "what-if" chart of the tank with and without the shipment.
6. **Decide and submit.** The operator clicks Approve. The backend re-fetches the world, re-checks, then sends
   `POST /v1/allocations` with the key `32-station-mirpur-DIESEL-route-gazipur-mirpur-0`. The dashboard's History tab
   then shows the shipment go PENDING → IN_TRANSIT → ARRIVED.

---

## 5. Each part in detail

### 5.1 Sync: reading the world (`backend/app/runtime.py`)

- Every **2 seconds**, the backend fetches all resources **at the same time**: instance (tick, time),
  depots, stations, routes, supply arrivals, events, allocations, metrics.
- It also listens to the simulator's **SSE stream**. When the stream says "tick happened", it fetches immediately
  instead of waiting for the next 2-second poll. If the stream dies, polling carries on, so nothing depends on it.
- Only a **complete** fetch replaces the saved state. If any part fails, we keep the previous "last good state" and
  mark the screen "Degraded". The dashboard never shows half-updated or empty data.
- Demand history: on startup we fetch the last 2,000 rows, then 200 per cycle, and save them in Postgres.
- **Reset detection:** if the tick goes backwards, or the stream announces a reset, we wipe our memory and cancel
  open recommendations, because they belong to a world that no longer exists.

### 5.2 Forecast (`shared/fuelcore/forecast.py`, `prediction/app/main.py`)

```text
baseline per tick = daily liters for the station's profile and fuel
                    ÷ ticks per day (1440 ÷ tick_minutes)
                    × hour-of-day factor (busy vs off-peak hours)
                    × region demand factor (Dhaka 1.00, Chattogram 1.08)
                    × station demand multiplier (changed by demand spike events)
```

- **Calibration** (prediction service only): compare actual demand with the baseline over the last 16 ticks.
  If actual demand ran 10% higher, multiply the forecast by 1.10. The ratio is kept between 0.5 and 3.0 so one odd
  reading can't send it wild.
- **Confidence** = 1 − average forecast error (MAPE) over those 16 ticks. The noise in this world is about 10%, so
  confidence is usually around 0.9.
- **Spike detection:** a station is flagged when its multiplier is above 1.0, or actual demand ran over 1.3× the
  baseline for 4 ticks in a row.
- **Seeing the future:** a demand spike can be scheduled for later. We read the event list and put the spike into the
  forecast for those future ticks, so recommendations appear **before** the spike hits.
- **Fallback:** if the prediction service doesn't answer within 1 second, the backend runs the same formula itself,
  without calibration, and labels recommendations "fallback".

### 5.3 Risk (`shared/fuelcore/projection.py`)

- For each station-fuel, walk forward 48 ticks (12 hours): add fuel arriving on each tick, subtract forecast demand.
  The first tick where the tank would go below zero is **ticks to stockout**.
- **Risk score from 0 to 1:** 1.0 when a shipment ordered now can no longer arrive before the stockout; 0.0 when
  there are 6 or more hours of slack; linear in between.
- Colours on the dashboard: red ≥ 0.7, amber ≥ 0.4, green below that.

### 5.4 Decision engine (`backend/app/engine.py`)

Runs once per tick. It is **greedy**: handle the most urgent case first, then the next, keeping track of what is
left.

1. **Who needs fuel?** Stockout within lead time + 2 hours, **or** tank projected below 35% when a shipment could land.
   Stations in OUTAGE are skipped: they cannot receive fuel.
2. **In what order?** Highest risk first, then most liters of unmet demand expected.
3. **How much?** Refill toward **85%** of the tank, then take the smallest of:
   - space in the tank (capacity − inventory − fuel already on the way),
   - the route's max load,
   - the depot's stock after its **reserve**,
   - the depot's dispatch capacity left this tick.

   Skip it if the result is under 500 L.
4. **Which route?** The fastest route that works. If the main route is disrupted, about to be disrupted, or its
   depot is short, use the cross-region backup, and the reason says why. Tongi and Cox's Bazar have only one route
   each; if it is cut, a red **"No route"** alert warns that they are a single point of failure.
5. **Depot reserve:** a depot keeps back what its own stations will need until its next delivery arrives. When fuel is
   scarce, its stations share it in proportion to need, so no fuel sits idle while another station runs dry.
6. **Pre-check** (`backend/app/validation.py`): every shipment is checked against the simulator's rules, **in the
   same order the simulator checks them**, before it is proposed:

| Order | Rule | Rejection code |
|---|---|---|
| 1 | Key never used before | IDEMPOTENCY_KEY_MISMATCH |
| 2 | Depot, station, route all exist | NOT_FOUND |
| 3 | Route really connects that depot to that station | ROUTE_MISMATCH |
| 4 | Depot is OPEN or CONSTRAINED | DEPOT_CLOSED |
| 5 | Station is OPEN | STATION_CLOSED |
| 6 | Route is AVAILABLE | ROUTE_DISRUPTED |
| 7 | Quantity ≤ route max | ROUTE_CAPACITY_EXCEEDED |
| 8 | Depot has the fuel | INSUFFICIENT_INVENTORY |
| 9 | Depot hasn't shipped too much this tick | DISPATCH_CAPACITY_EXCEEDED |
| 10 | Station tank has room | DESTINATION_CAPACITY_EXCEEDED |
| + | Our extra rule: no disruption scheduled to start now | ROUTE_DISRUPTION_SCHEDULED |
| + | Our extra rule: inventory + inbound + quantity fits the tank | DESTINATION_OVERFLOW_RISK |

### 5.5 Recommendations and approvals (`backend/app/recommendations.py`)

```text
            ┌──────────► REJECTED   (operator clicked Reject)
            ├──────────► EXPIRED    (nobody acted within 4 ticks)
            ├──────────► SUPERSEDED (the world changed and it would now fail)
 OPEN ──────┼──────────► FAILED     (pre-check or simulator said no; code is logged)
            │
            └─ Approve / auto ─► SUBMITTING ─► SUBMITTED ─► allocation PENDING → IN_TRANSIT → ARRIVED
                                     │
                                     └─ simulator down? stay SUBMITTING and resend with the SAME key
```

- **Three modes** (switch at the top of the dashboard):
  - `manual`: every shipment needs a click. This is the default for the demo.
  - `auto`: the system submits everything itself. This is needed at full speed, where a simulated day passes in about 12 seconds.
  - `hybrid`: only low-risk, high-confidence, non-fallback shipments go automatically; the rest wait for a human.
- **On Approve**, the backend re-fetches the world first and re-checks. If the tank filled up in the meantime, it
  shrinks the quantity to fit instead of failing.
- **A 409 is never blindly retried.** The code is written on the decision log. The next tick produces a fresh
  recommendation with a new key if the need is still there.
- **A 503 or timeout is resent with the same key.** That is safe: if the first attempt actually went through, the
  simulator just returns it again (200 or 201, both treated as success).
- **Auto mode pauses** while data is stale or the circuit breaker is open, because it should not act on data it
  can't trust.
- Every action goes into the **decision log**: what, who (operator, auto or system), when, the allocation id, its live
  status and any failure reason.

### 5.6 Dashboard (`frontend/src/screens/`)

| Tab | What it shows |
|---|---|
| **Network** | Tick, clock, service level; 4 station cards (a bar per fuel, hours to stockout, risk colour, spike badge); depots with the next delivery; routes; a map; click a station to see a forecast-vs-actual chart |
| **Recommendations** | One card per recommendation: reason, quantity, route, risk before → after, confidence, alternative, what-if chart, Approve and Reject |
| **History & events** | Decision log with live shipment status, the shipments list (cancel PENDING ones), and crisis events |
| **System health** | Simulator (with breaker state), database, prediction, live stream, decision engine; link to Grafana |
| **Demo** | Buttons to run, pause, step and reset the simulator, and to inject any event or fault, including one-click presets for the demo |

Banners for **Degraded**, **Stale data** and **Fallback forecast** stay at the top whenever they are active.

### 5.7 Observability

- Both services expose `/metrics` for Prometheus: simulator call results and latency, breaker state, SSE connected,
  decision cycle time, recommendations by outcome, **409s by code**, service level, stale and fallback flags, and
  forecast error per fuel.
- Grafana has one ready-made dashboard (`observability/grafana/dashboards/fuel-ops.json`).
- Logs are one JSON line per event with `tick`, `component` and `event` fields: `./run.sh logs`.

---

## 6. What happens when things break

| Failure | How we notice | What the platform does |
|---|---|---|
| Simulator slow (`latency`) | A call takes over 2 s | Counts as a failure; retries; shows in Grafana latency |
| Simulator down (`unavailable`) | 503 with `FAULT_INJECTED` | Retries 3× with growing, randomised waits. After 5 failures in a row the **circuit breaker** opens: stop calling for 10 s, then try once. The screen keeps the last good state with a Degraded banner, and auto mode holds |
| Random errors (`error_rate`) | Some calls return 503 | Same retries; most cycles still succeed |
| Old data (`stale_data`) | Header `X-Simulator-Stale: true` | Stale banner; auto mode stops submitting |
| Live stream down (`stream_disconnect`) | 503 on `/v1/stream` | Reconnects with backoff; the 2-second polling keeps data fresh anyway |
| Prediction service down | No answer within 1 s | Backend uses the same formula without calibration; recommendations labelled "fallback" |
| Database down | Connection error | Keeps running from memory; writes wait in a queue and are retried |
| Simulator reset | Tick goes backwards | Clears memory and open recommendations |

The simulator returns errors in two different shapes (`{"error": {...}}` for faults, `{"detail": {...}}` for
rejections). We read both.

---

## 7. Things we discovered about the simulator

We probed the real simulator before writing the engine. These facts are not all in the guide, and they shape our
rules:

- **Fuel that overflows a tank is lost.** A 5,000 L shipment into a nearly full tank delivered only 1,370 L. So we
  always count fuel already on the way before sizing a shipment.
- **A route disrupted in the same tick a shipment is created makes it FAIL**, and the fuel is not given back. So we skip
  routes whose disruption is scheduled to start now.
- **A shipment leaves in the same tick it is created** and arrives `transit_ticks` later. The depot's stock drops
  immediately.
- **The dispatch limit only counts shipments created this tick**, not ones already on the road.
- **Doing nothing collapses:** service level is 1.0 at tick 48, 0.88 at tick 96, 0.46 at tick 192 and 0.18 at tick 480.

---

## 8. Demo script

Everything is on the dashboard's **Demo** tab (preset buttons). The world is deterministic, so it plays the same every
time.

| Step | Do | Point at |
|---|---|---|
| 1 | Open **System health** | All 5 components green; Grafana link |
| 2 | Demo → **Reset**, then **Run** (or Step 10) | Network tab: all stations healthy, service level 100% |
| 3 | Preset **Dhaka demand spike ×1.8** | Spike badges on Mirpur and Tongi; hours to stockout drop; recommendations appear. Read one reason aloud, show risk before → after and the what-if chart, click **Approve**. History shows PENDING → IN_TRANSIT → ARRIVED |
| 4 | Preset **Disrupt Gazipur → Mirpur** | The next Mirpur recommendation uses the Patiya backup route and explains why |
| 5 | Preset **Disrupt Gazipur → Tongi** | Red "No route to Tongi" alert: a single point of failure |
| 6 | Preset **Supply shortfall Gazipur ×0.5** | Depot projection drops; the reserve rule caps shipments, and the reason names it |
| 7 | Preset **Unavailable 30 s** | Degraded banner; the last good state stays on screen; data age counts up; auto mode holds; it recovers alone |
| 8 | Presets **Stale data**, then **Stream disconnect** | Stale banner; Health shows the stream down while data stays fresh |
| 9 | Terminal: `docker compose stop prediction` | "Fallback" labels and banner; `docker compose start prediction` brings calibration back |
| 10 | Switch to **Auto**, run; open Grafana; run `./run.sh compare` | Service level stays 100%; 409s at zero; do-nothing vs platform numbers |

---

## 9. Questions judges may ask

**Why not machine learning?** The world is small (12 pairs) and follows a documented formula. A formula plus
calibration is accurate (about 90% confidence), explainable in one sentence, and cannot surprise the operator. The
brief says complexity does not score by itself.

**How do you avoid 409s?** Every shipment is pre-checked against the simulator's own rules in the simulator's own order
(section 5.4), plus two stricter rules for problems the simulator allows but that lose fuel. There is one unit test per
409 code.

**What if the simulator goes down in the middle of a shipment?** The request is resent with the same idempotency
key. If the first attempt landed, the simulator returns that same shipment instead of creating a second one.

**Why is SSE only a hint?** The stream has no replay: if we miss an event, it is gone. So we treat events as "go and look",
and REST is always the truth. Polling every 2 s works even with the stream down.

**Why an auto mode if there's a human approval flow?** At normal speed a simulated day passes in about 12 seconds; no
human can approve that fast. Hybrid mode is the middle ground: routine shipments go automatically, risky ones wait
for a person.

**How do you share scarce fuel fairly?** The depot reserve rule: when a depot can't cover everyone until its next
delivery, its stations get a share in proportion to their need.

**What happens after the last supply delivery (tick 212)?** Stations eventually run dry whatever anyone does, because
the scenario stops supplying fuel. Our advantage is largest in the first two to three days.

---

## 10. Where the code lives

```text
run.sh                      one command to run everything
docker-compose.yml          the 7 services
shared/fuelcore/            forecast math shared by backend and prediction
  world.py                  demand profiles, hour factors, time helpers
  forecast.py               baseline, event-aware multiplier, calibration
  projection.py             tank projection, risk score
  analyze.py                ties it together: snapshot in → forecasts, risk, depot projection out
prediction/app/main.py      prediction service: POST /forecast, POST /risk, metrics
backend/app/
  main.py                   starts the app
  runtime.py                sync loop, SSE handling, reset detection, the per-tick decision cycle
  sim/client.py             simulator client: timeouts, retries, breaker, stale header
  sim/breaker.py            circuit breaker
  sim/sse.py                live stream listener with reconnect
  sim/errors.py             reads both error shapes
  forecaster.py             calls prediction service, falls back locally
  engine.py                 the decision engine (who, how much, which route, reason text)
  validation.py             pre-check in the simulator's order
  recommendations.py        recommendation lifecycle, approve/reject/auto, decision log
  persistence.py            Postgres, write-behind with retry
  explain.py                optional LLM explanations (Cerebras), template text as fallback
  api.py, views.py          the dashboard API
frontend/src/               React dashboard (screens/, components/, api/)
observability/              Prometheus config, Grafana dashboard
scripts/e2e.py              end-to-end proof against the real simulator
scripts/compare.py          do-nothing vs platform
loadtest/k6.js              50 users for 1 minute on the busiest endpoints
.github/workflows/ci.yml    lint, tests, build, full-stack smoke test on every push
```

---

## 11. Tests and results

Everything below was run on this machine against the real stack (official simulator image, real containers).
Nothing in this table is mocked.

```bash
./run.sh compare      # do nothing vs platform
./run.sh e2e 200      # auto mode, 200 ticks
./run.sh verify       # 27 live checks
./run.sh loadtest     # k6
```

### Do nothing vs our platform (`scripts/compare.py`, 192 ticks, same seed, same 3 crises)

| | Service level | Unmet liters | Failed shipments | 409s |
|---|---|---|---|---|
| Do nothing | 0.427 | 115,061 | none sent | none sent |
| **Our platform, auto mode** | **1.000** | **0** | **0** | **0** |

Without crises, doing nothing gives 0.88 at tick 96, 0.46 at tick 192 and 0.18 at tick 480. Our platform stays at
1.000 for 200 ticks (`scripts/e2e.py`, 0 failures, 0 × 409).

### Live crisis, fault and fallback checks (`scripts/verify_live.py`): 27 of 27 pass

| Area | What we inject for real | What we check |
|---|---|---|
| Crisis | Dhaka demand spike ×1.8 | Mirpur and Tongi flagged; recommendations with reasons appear; approve creates a real shipment that departs |
| Crisis | Gazipur → Mirpur road cut | Mirpur switches to the Patiya backup route, and nothing is proposed on the cut road |
| Crisis | Gazipur → Tongi road cut | "No route to Tongi … single point of failure" alert |
| Crisis | Supply shortfall ×0.5 at Gazipur | Future deliveries halved; the depot reserve adjusts |
| Crisis | Station outage at Cox's Bazar | Shown as OUTAGE, alerted, no shipments proposed |
| Crisis | All of the above | 0 shipments rejected by the simulator |
| Fault | `unavailable` 15 s | Degraded banner, last good state kept, breaker opens, auto holds, recovers alone |
| Fault | `latency` 2.5 s (over the 2 s timeout) | Treated as failure, degraded, recovers |
| Fault | `error_rate` 25% (the default) | Data stays fresh (max age 3.1 s), never degraded |
| Fault | `stale_data` | Stale banner, auto submissions paused, clears after |
| Fault | `stream_disconnect` + simulator restart | Live stream down, polling keeps data fresh, stream reconnects after |
| Fallback | `docker compose stop prediction` | Backend switches to the baseline formula, recommendations labelled "fallback", switches back |
| Fallback | `docker compose stop postgres` | Health shows DB down, API (2 ms) and engine keep running, queued writes flushed on return |
| Reset | `/admin/reset` | Detected; state and open recommendations cleared |

At a harsher 50% error rate, data stays fresh most of the time (median 2.4 s), and the circuit breaker opens on 5
straight failures, as designed.

### Load test (`loadtest/k6.js`, 50 virtual users, 1 minute, `/api/state` + `/api/recommendations`)

| Requests | Throughput | Failed | Median | p95 | p99 | Target |
|---|---|---|---|---|---|---|
| 167,072 | 2,784 req/s | 0.00% | 15.9 ms | **37.2 ms** | 45.3 ms | p95 < 300 ms ✓ |

### Unit tests: 65 pass

- `shared/`: 34 tests. Forecast math, hour factors, calibration, spike detection, projection, risk.
- `backend/`: 26 tests. One per simulator 409 code, both error shapes, idempotency keys, engine rules (backup route,
  no-route alert, dispatch limits), and retries, circuit breaker, stale header and SSE parsing. Also a regression test
  for a bug the live run found (below).
- `prediction/`: 5 tests. The service's API and metrics.

### A bug the live checks caught, and the fix

The first live run showed 8 × `DISPATCH_CAPACITY_EXCEEDED` from the simulator. In auto mode, several recommendations
were submitted in the same tick, and each was checked against the snapshot on its own, so together they exceeded a
depot's per-tick dispatch limit. Now every batch carries a running total of what it has already sent in that tick
(`RecommendationService.submit_auto`), and the second shipment is resized to the capacity left. After the fix: 0
rejections across all runs.
