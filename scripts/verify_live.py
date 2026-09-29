#!/usr/bin/env python3
"""Live verification against the running stack: crises, faults, fallbacks, resets. No mocks.

Every check injects the condition into the real simulator (or stops a real container) and observes
the backend's own API. Prints PASS/FAIL per check and exits non-zero if any fail.

Usage: python3 scripts/verify_live.py            (needs ./run.sh up; takes about 4 minutes)
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

SIM = "http://localhost:8000"
API = "http://localhost:8001"
ROOT = Path(__file__).resolve().parent.parent
RESULTS: list[tuple[str, bool, str]] = []


def call(method: str, url: str, body: Any = None, timeout: float = 20) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def sim(method: str, path: str, body: Any = None) -> Any:
    return call(method, SIM + path, body)


def api(method: str, path: str, body: Any = None) -> Any:
    return call(method, API + path, body)


def state() -> dict:
    return api("GET", "/api/state")


def health() -> dict:
    return api("GET", "/health")


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True)


def wait_until(fn: Callable[[], Any], timeout: float, every: float = 0.5) -> Any:
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        try:
            last = fn()
            if last:
                return last
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, ConnectionError):
            pass
        time.sleep(every)
    return last


def step(n: int = 1) -> int:
    tick = 0
    for _ in range(n):
        tick = sim("POST", "/admin/step")["tick"]
        wait_until(lambda t=tick: health()["components"]["engine"]["last_cycle_tick"] == t, 20, 0.1)
    return tick


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


def event(kind: str, duration: int, **params: Any) -> None:
    tick = state()["tick"]
    sim("POST", "/admin/events", {"type": kind, "start_tick": tick, "duration_ticks": duration, "parameters": params})


def fault(kind: str, seconds: int, **params: Any) -> None:
    sim("POST", "/admin/faults", {"type": kind, "duration_seconds": seconds, "parameters": params})


def conflicts() -> float:
    """Total 409s the simulator returned to the backend (Prometheus counter)."""
    text = urllib.request.urlopen(f"{API}/metrics", timeout=5).read().decode()
    return sum(float(line.rsplit(" ", 1)[1]) for line in text.splitlines()
               if line.startswith("allocation_conflicts_total{"))


def open_recs() -> list[dict]:
    return api("GET", "/api/recommendations")["items"]


def fresh_start(mode: str = "manual") -> None:
    sim("POST", "/admin/pause")
    sim("POST", "/admin/faults/clear")
    api("PUT", "/api/settings", {"mode": mode})
    sim("POST", "/admin/reset")
    wait_until(lambda: state()["tick"] == 0 and not state()["degraded"], 20)
    wait_until(lambda: health()["components"]["engine"]["last_cycle_tick"] == 0, 20)


# ----------------------------------------------------------------------------------------------- crises


def crises() -> None:
    print("\nCrisis response (real events injected into the simulator)")
    fresh_start("manual")
    conflicts_before = conflicts()
    step(4)

    event("demand_spike", 48, region_ids=["region-dhaka"], multiplier=1.8)
    step(1)
    s = state()
    spiking = {st["id"] for st in s["stations"] if st["spike"]}
    check("demand spike: Dhaka stations flagged", {"station-mirpur", "station-tongi"} <= spiking, f"flagged {sorted(spiking)}")
    rec = wait_until(lambda: [r for r in open_recs() if r["station_id"] in ("station-mirpur", "station-tongi")]
                     or (step(1) and None), 120, 0)
    check("demand spike: recommendations for Dhaka appear", bool(rec),
          (rec[0]["reason"][:110] + "...") if rec else "none")

    if rec:
        out = api("POST", f"/api/recommendations/{rec[0]['id']}/approve")
        check("approve: allocation created in the simulator", out["ok"] and out["recommendation"]["allocation_id"],
              f"allocation {out['recommendation']['allocation_id']}, {out['recommendation']['allocation_status']}")
        step(1)
        alloc = next(a for a in sim("GET", "/v1/allocations") if a["id"] == out["recommendation"]["allocation_id"])
        check("approve: shipment departs", alloc["status"] in ("IN_TRANSIT", "ARRIVED"), alloc["status"])

    event("route_disruption", 30, route_ids=["route-gazipur-mirpur"])
    step(1)
    backup = wait_until(lambda: [r for r in open_recs() if r["station_id"] == "station-mirpur"
                                 and r["route_id"] == "route-patiya-mirpur"] or (step(1) and None), 120, 0)
    check("route disruption: Mirpur switches to Patiya backup", bool(backup),
          (backup[0]["reason"][-160:]) if backup else "no backup recommendation")
    mirpur_primary = [r for r in open_recs() if r["route_id"] == "route-gazipur-mirpur"]
    check("route disruption: nothing proposed on the disrupted route", not mirpur_primary)

    event("route_disruption", 30, route_ids=["route-gazipur-tongi"])
    step(1)
    alerts = [a for a in state()["alerts"] if a["kind"] == "no_route" and a.get("station_id") == "station-tongi"]
    check("single route cut: 'No route to Tongi' alert", bool(alerts), alerts[0]["message"][:100] if alerts else "")

    before = {s["id"]: s["quantity"] for s in sim("GET", "/v1/supply-arrivals")
              if s["depot_id"] == "depot-gazipur" and s["status"] != "ARRIVED"}
    event("supply_shortfall", 1, depot_ids=["depot-gazipur"], factor=0.5)
    step(1)
    after = {s["id"]: s["quantity"] for s in sim("GET", "/v1/supply-arrivals") if s["id"] in before}
    halved = all(abs(after[k] - before[k] * 0.5) < 1 for k in before)
    gz = next(d for d in state()["depots"] if d["id"] == "depot-gazipur")
    reserve = sum(f["reserve_liters"] for f in gz["fuels"])
    check("supply shortfall: future Gazipur arrivals halved and seen by the platform", halved and bool(before),
          f"{len(before)} arrivals, depot reserve now {reserve:,.0f} L")

    event("station_outage", 6, station_ids=["station-coxsbazar"])
    step(1)
    s = state()
    cox = next(st for st in s["stations"] if st["id"] == "station-coxsbazar")
    outage_alert = any(a["kind"] == "outage" for a in s["alerts"])
    cox_recs = [r for r in open_recs() if r["station_id"] == "station-coxsbazar" and r["created_tick"] == s["tick"]]
    check("station outage: shown, alerted, no shipments proposed", cox["status"] == "OUTAGE" and outage_alert
          and not cox_recs, f"status {cox['status']}")

    new_409 = conflicts() - conflicts_before
    check("no simulator 409s during crises", new_409 == 0, f"{new_409:.0f} rejected by the simulator")


# ----------------------------------------------------------------------------------------------- faults


def faults() -> None:
    print("\nFailure handling (real faults injected into the simulator)")
    fresh_start("auto")
    step(3)
    tick_before = state()["tick"]

    fault("unavailable", 15)
    degraded = wait_until(lambda: state()["degraded"] and state(), 20)
    check("unavailable: Degraded banner, last good state still served",
          bool(degraded) and degraded["tick"] == tick_before and len(degraded["stations"]) == 4,
          f"tick {degraded['tick'] if degraded else '?'}, reason: {(degraded or {}).get('degraded_reason', '')[:70]}")
    h = health()["components"]
    check("unavailable: circuit breaker opens", h["simulator"]["breaker"] in ("open", "half_open"),
          f"breaker {h['simulator']['breaker']}, failures {h['simulator']['consecutive_failures']}")
    step(1)  # the tick advances in the simulator while our reads are failing
    held = health()["components"]["engine"]
    check("unavailable: auto mode holds (no submissions)", held["paused_reason"] is not None or held["last_cycle_tick"]
          == tick_before, f"paused_reason={held['paused_reason']}")
    recovered = wait_until(lambda: not state()["degraded"] and health()["components"]["simulator"]["breaker"] == "closed",
                           40)
    check("unavailable: recovers on its own after the fault ends", bool(recovered),
          f"tick {state()['tick']}, breaker {health()['components']['simulator']['breaker']}")

    fault("latency", 12, delay_ms=2500)
    slow = wait_until(lambda: state()["degraded"], 25)
    check("latency 2.5 s (> 2 s timeout): treated as failure, degraded", bool(slow))
    check("latency: recovers", bool(wait_until(lambda: not state()["degraded"], 40)))

    fault("error_rate", 20, rate=0.25)  # the simulator's documented default
    ages, degraded_seen = [], 0
    for _ in range(12):
        s = state()
        ages.append(s["data_age_s"] or 0)
        degraded_seen += s["degraded"]
        time.sleep(1.5)
    sim("POST", "/admin/faults/clear")
    check("error_rate 25%: retries keep data fresh", max(ages) < 6 and degraded_seen == 0, f"max data age {max(ages):.1f}s, "
          f"degraded {degraded_seen}/12 samples")

    fault("stale_data", 15)
    stale = wait_until(lambda: state()["stale"], 10)
    step(1)
    paused = health()["components"]["engine"]["paused_reason"]
    check("stale_data: Stale banner and auto submissions paused", bool(stale) and paused is not None, f"paused_reason={paused}")
    check("stale_data: clears after the fault", bool(wait_until(lambda: not state()["stale"], 30)))

    # A live stream is not cut by the fault itself, so restart the simulator process while stream_disconnect is on.
    fault("stream_disconnect", 40)
    compose("restart", "simulator")
    down = wait_until(lambda: not health()["components"]["sse"]["connected"], 30)
    back = wait_until(lambda: sim("GET", "/v1/health")["status"] == "ok", 90)
    fresh = wait_until(lambda: state()["data_age_s"] is not None and state()["data_age_s"] < 5, 40)
    sse = health()["components"]["sse"]
    check("stream_disconnect: SSE down, polling keeps data fresh", bool(down) and bool(back) and bool(fresh)
          and not sse["connected"], f"sse connected={sse['connected']}, reconnect attempts={sse['reconnects']}")
    sim("POST", "/admin/faults/clear")
    reconnected = wait_until(lambda: health()["components"]["sse"]["connected"], 60)
    check("stream_disconnect: SSE reconnects after the fault", bool(reconnected),
          f"reconnect attempts={health()['components']['sse']['reconnects']}")


# ----------------------------------------------------------------------------------------------- fallbacks


def fallbacks() -> None:
    print("\nFallback behaviour (real containers stopped)")
    fresh_start("manual")
    step(2)

    compose("stop", "prediction")
    step(1)
    s, h = state(), health()["components"]["prediction"]
    check("prediction down: backend falls back to baseline formula", s["fallback"] and h["fallback"],
          f"prediction status {h['status']}: {h['detail'][:60]}")
    fb = wait_until(lambda: [r for r in open_recs() if r["fallback"]] or (step(1) and None), 90, 0)
    check("prediction down: recommendations still produced, labelled fallback", bool(fb),
          f"{len(fb or [])} fallback recommendations")
    compose("start", "prediction")
    wait_until(lambda: health()["components"]["prediction"]["status"] != "down" and step(1) and not state()["fallback"],
               60, 1)
    check("prediction back: calibrated forecasts resume", not state()["fallback"])

    compose("stop", "postgres")
    step(1)
    db = wait_until(lambda: health()["components"]["database"]["status"] == "down" and health(), 30)
    t0 = time.perf_counter()
    s = state()
    ms = (time.perf_counter() - t0) * 1000
    step(2)
    check("database down: health shows it, API and engine keep running", bool(db) and s["tick"] is not None
          and health()["components"]["engine"]["last_cycle_tick"] == state()["tick"],
          f"/api/state in {ms:.0f} ms, queued writes {health()['components']['database']['pending_writes']}")
    compose("start", "postgres")
    drained = wait_until(lambda: health()["components"]["database"]["status"] == "up"
                         and health()["components"]["database"]["pending_writes"] == 0, 60)
    check("database back: queued writes flushed", bool(drained))

    tick = state()["tick"]
    sim("POST", "/admin/reset")
    reset = wait_until(lambda: state()["tick"] == 0 and state(), 20)
    check("simulator reset: detected, state and open recommendations cleared",
          bool(reset) and not [r for r in open_recs() if r["created_tick"] > 0], f"tick {tick} -> 0")


def main() -> int:
    started = time.time()
    for section in (crises, faults, fallbacks):
        try:
            section()
        except Exception as exc:  # report and continue with the next section
            check(f"{section.__name__} aborted", False, f"{type(exc).__name__}: {exc}")
    sim("POST", "/admin/faults/clear")
    sim("POST", "/admin/pause")
    api("PUT", "/api/settings", {"mode": "manual"})
    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed in {time.time() - started:.0f}s")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
