# Fuel Supply Operations Platform

A decision-support platform on top of the BUP Fuel Supply Simulator. It reads the network, forecasts station demand,
flags stockout risk, recommends shipments with a reason, and submits approved ones via `POST /v1/allocations`.
The simulator is the world; this platform is the brain and the operator's screen.

## Run

```bash
./run.sh              # builds and starts everything, waits until healthy, prints URLs
./run.sh demo         # same, then resets the simulator and starts the clock
./run.sh e2e 200      # same, then runs the end-to-end check (auto mode, 200 ticks)
./run.sh compare      # do-nothing vs platform on the same seed and events
./run.sh logs | stop | down
```

`run.sh` creates `.env` from `.env.example` on first run (SIMULATION_SPEED=1, simulator starts paused).

| URL | What |
|---|---|
| http://localhost:3000 | Operator dashboard: Network, Recommendations, History & events, System health, Demo control |
| http://localhost:8001/docs | Backend API (Swagger) |
| http://localhost:3001 | Grafana, dashboard "Fuel Supply Operations" (admin/admin) |
| http://localhost:9090 | Prometheus |
| http://localhost:8000/admin | Simulator console |

## Architecture

```
Frontend :3000 (React, nginx) --/api--> Backend :8001 --REST poll + SSE trigger + POST--> Simulator :8000
                                          |    \--> Prediction :8002 (stateless; 1 s timeout, backend falls back)
                                          \--> Postgres :5432 (write-behind: decisions, recommendations, demand)
Prometheus :9090 + Grafana :3001 scrape backend and prediction
```

- **Sync:** every 2 s, or when SSE reports a change, the backend fetches the full state concurrently. Only a complete
  fetch replaces the in-memory *last good state*. The API always serves from memory, so it never goes blank.
- **Forecast:** baseline = daily liters / ticks_per_day × hour factor × region factor × station multiplier.
  Multipliers are rebuilt from `demand_spike` events, so scheduled spikes are forecast before they start.
  The prediction service calibrates against the last 16 ticks (clamped 0.5 to 3.0) and reports MAPE-based confidence.
  If it is down, the backend runs the same formulas uncalibrated (`shared/fuelcore`) and labels recommendations "fallback".
- **Decision engine** (once per tick):
  - Candidates: stockout within lead time + 2 h, or projected level under 35%.
  - Quantity: refill toward 85%, capped by headroom (capacity - inventory - inbound), route max, depot reserve and dispatch left this tick.
  - Route: shortest usable route, with a cross-region backup when the primary is disrupted or its depot is short.
  - Checks: every request is pre-checked in the simulator's own validation order. Two stricter platform rules sit on top:
    - no route whose disruption starts at departure (the simulator would mark it FAILED);
    - no overflow (fuel above capacity is lost on arrival).
- **Approvals:**
  - Modes: `manual`, `auto`, and `hybrid` (auto only for low-risk, high-confidence, non-fallback recommendations).
  - Recommendations expire after 4 ticks, and approval re-checks against a fresh fetch.
  - 409s are logged, never blindly retried. 503s and timeouts are replayed with the same idempotency key.
  - Auto mode holds while data is stale or the circuit breaker is open.
- **Resilience:**
  - Timeouts of 2 s, and GETs retried 3× with jittered backoff.
  - A circuit breaker opens after 5 straight failures and half-opens after 10 s.
  - SSE reconnects with backoff, and polling carries on regardless.
  - Resets are detected (tick goes backwards or a `simulator.notice`), which clears state and open recommendations.
- **LLM explanations (optional):** set `LLM_EXPLANATIONS=true` and `CEREBRAS_API_KEY` in `.env`. The template text stays
  if the call fails or exceeds 1.5 s.

## Demo (PRD 8)

Use the dashboard's **Demo control** tab (it proxies `/admin/*`), or call the simulator directly:

1. System health is all green. Reset, then step or run: all stations healthy, service level 1.0.
2. Demand spike on `region-dhaka` ×1.8: spike badges on Mirpur and Tongi, and recommendations with reasons. Approve them.
3. Disrupt `route-gazipur-mirpur`: the next Mirpur recommendation uses the Patiya backup and says why.
4. Disrupt `route-gazipur-tongi`: a "No route to Tongi… single point of failure" alert appears.
5. `supply_shortfall` on a depot: the depot projection drops, and the reserve rule caps outbound shipments.
6. `unavailable` fault for 30 s: a Degraded banner appears, the last good state stays on screen, and auto mode holds.
7. `stale_data`, then `stream_disconnect`: a stale banner appears, and SSE shows disconnected while polling keeps data fresh.
8. `docker compose stop prediction`: recommendations switch to "fallback"; `docker compose start prediction` switches them back.
9. `python3 scripts/compare.py`: do-nothing vs platform on the same seed and events.

## Tests

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e 'shared[dev]' -e 'backend[dev]' -e 'prediction[dev]'
pytest -q shared && pytest -q backend && (cd prediction && pytest -q)
python3 scripts/e2e.py --ticks 200            # against the running stack
k6 run loadtest/k6.js                         # or: docker run --rm -i --network host grafana/k6 run - < loadtest/k6.js
```

## Results

See the "Results" section below. It is filled in from real runs.
