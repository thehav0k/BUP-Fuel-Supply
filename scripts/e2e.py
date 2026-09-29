#!/usr/bin/env python3
"""End-to-end check against the running stack (PRD 7).

reset -> pause -> auto mode -> step N ticks (waiting for the backend to process each) ->
assert service level >= threshold and no unexpected 409s.

Usage: python scripts/e2e.py --ticks 200 --min-service-level 0.97
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

SIM = "http://localhost:8000"
API = "http://localhost:8001"


def call(method: str, url: str, body: object | None = None, timeout: float = 15) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def wait_processed(tick: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        eng = call("GET", f"{API}/health")["components"]["engine"]
        if eng.get("last_cycle_tick") == tick:
            return
        time.sleep(0.05)
    raise TimeoutError(f"backend did not process tick {tick}")


def conflicts() -> dict[str, float]:
    text = urllib.request.urlopen(f"{API}/metrics", timeout=5).read().decode()
    out: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("allocation_conflicts_total{"):
            code = line.split('code="')[1].split('"')[0]
            out[code] = float(line.rsplit(" ", 1)[1])
    return out


def run(ticks: int, mode: str, events: list[dict] | None = None, quiet: bool = False) -> dict:
    call("POST", f"{SIM}/admin/pause")
    call("POST", f"{SIM}/admin/faults/clear")
    call("PUT", f"{API}/api/settings", {"mode": mode})
    call("POST", f"{SIM}/admin/reset")
    time.sleep(1.5)  # let the backend see the reset
    for e in events or []:
        call("POST", f"{SIM}/admin/events", e)
    before = conflicts()
    wait_processed(0, timeout=30)
    for i in range(ticks):
        tick = call("POST", f"{SIM}/admin/step")["tick"]
        wait_processed(tick)
        if not quiet and (i + 1) % 25 == 0:
            m = call("GET", f"{SIM}/v1/metrics")
            print(f"  tick {tick:4d}  service_level {m['service_level']:.4f}", flush=True)
    metrics = call("GET", f"{SIM}/v1/metrics")
    after = conflicts()
    new_409 = {k: v - before.get(k, 0) for k, v in after.items() if v - before.get(k, 0) > 0}
    return {"metrics": metrics, "conflicts": new_409}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=200)
    ap.add_argument("--min-service-level", type=float, default=0.97)
    args = ap.parse_args()
    result = run(args.ticks, "auto")
    call("PUT", f"{API}/api/settings", {"mode": "manual"})
    m = result["metrics"]
    print(json.dumps({"service_level": m["service_level"], "unmet_liters": m["unmet_demand_liters"],
                      "allocation_failures": m["allocation_failures"], "409s": result["conflicts"]}, indent=2))
    ok = m["service_level"] >= args.min_service_level and not result["conflicts"] and m["allocation_failures"] == 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
