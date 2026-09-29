#!/usr/bin/env python3
"""Baseline comparison (PRD 9.1): same seed, same injected events, do-nothing vs our auto mode.

Usage: python scripts/compare.py --ticks 192
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from e2e import SIM, call, run

EVENTS = [
    {"type": "demand_spike", "start_tick": 20, "duration_ticks": 32,
     "parameters": {"region_ids": ["region-dhaka"], "multiplier": 1.8}},
    {"type": "route_disruption", "start_tick": 40, "duration_ticks": 16,
     "parameters": {"route_ids": ["route-gazipur-mirpur"]}},
    {"type": "supply_shortfall", "start_tick": 60, "duration_ticks": 1,
     "parameters": {"depot_ids": ["depot-patiya"], "factor": 0.5}},
]


def do_nothing(ticks: int) -> dict:
    call("POST", f"{SIM}/admin/pause")
    call("POST", f"{SIM}/admin/reset")
    time.sleep(1.0)
    for e in EVENTS:
        call("POST", f"{SIM}/admin/events", e)
    for _ in range(ticks):
        call("POST", f"{SIM}/admin/step")
    return call("GET", f"{SIM}/v1/metrics")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=192)
    args = ap.parse_args()
    # Manual mode with nobody approving = do nothing; the platform keeps running but sends no allocations.
    call("PUT", "http://localhost:8001/api/settings", {"mode": "manual"})
    base = do_nothing(args.ticks)
    ours = run(args.ticks, "auto", EVENTS, quiet=True)
    call("PUT", "http://localhost:8001/api/settings", {"mode": "manual"})
    print(json.dumps({
        "ticks": args.ticks,
        "events": [e["type"] for e in EVENTS],
        "do_nothing": {"service_level": base["service_level"], "unmet_liters": base["unmet_demand_liters"]},
        "platform_auto": {"service_level": ours["metrics"]["service_level"],
                          "unmet_liters": ours["metrics"]["unmet_demand_liters"],
                          "allocation_failures": ours["metrics"]["allocation_failures"],
                          "409s": ours["conflicts"]},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
