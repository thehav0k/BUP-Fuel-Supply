"""Static world knowledge from the simulator guide that the API does not expose.

Demand profiles and hour-of-day factors are only documented, not served, so they live here.
Calibration against observed demand absorbs any mismatch.
"""

from __future__ import annotations

from datetime import datetime, timedelta

FUELS: tuple[str, ...] = ("DIESEL", "PETROL", "OCTANE")

# Liters per simulated day at demand_multiplier 1.0 and region factor 1.0.
DAILY_LITERS: dict[str, dict[str, float]] = {
    "urban_high": {"DIESEL": 8500, "PETROL": 10500, "OCTANE": 5600},
    "industrial": {"DIESEL": 14000, "PETROL": 4500, "OCTANE": 2200},
    "highway": {"DIESEL": 10500, "PETROL": 11000, "OCTANE": 6200},
    "regional": {"DIESEL": 7200, "PETROL": 7600, "OCTANE": 3600},
}

# (busy hour ranges, inclusive) -> busy factor, else off-peak factor. Verified against live demand history.
_HOUR_FACTORS: dict[str, tuple[tuple[tuple[int, int], ...], float, float]] = {
    "industrial": (((6, 17),), 1.55, 0.45),
    "highway": (((6, 9), (16, 20)), 1.35, 0.75),
    "urban_high": (((7, 9), (16, 20)), 1.45, 0.70),
    "regional": (((7, 20),), 1.25, 0.65),
}


def hour_factor(profile: str, hour: int) -> float:
    spec = _HOUR_FACTORS.get(profile)
    if spec is None:
        return 1.0
    ranges, busy, off = spec
    return busy if any(lo <= hour <= hi for lo, hi in ranges) else off


def daily_liters(profile: str, fuel: str) -> float | None:
    return DAILY_LITERS.get(profile, {}).get(fuel)


def ticks_per_day(tick_minutes: float) -> float:
    return 1440.0 / tick_minutes


def ticks_per_hour(tick_minutes: float) -> float:
    return 60.0 / tick_minutes


def parse_sim_time(value: str) -> datetime:
    """The simulator returns naive ISO strings; the guide shows '+00:00'. Accept both, return naive UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None)


def time_at(base_time: datetime, base_tick: int, tick: int, tick_minutes: float) -> datetime:
    return base_time + timedelta(minutes=(tick - base_tick) * tick_minutes)
