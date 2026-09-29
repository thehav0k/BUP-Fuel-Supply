"""Baseline demand, event-aware multipliers and calibration.

baseline(tick) = daily liters / ticks_per_day x hour factor x region demand_factor x station multiplier(tick)

The station multiplier for past and future ticks is rebuilt from demand_spike events, so a spike that is
scheduled but not yet active is already in the forecast, and calibration is not fooled by a spike that
started halfway through the window.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .world import daily_liters, hour_factor, ticks_per_day, time_at

CALIBRATION_WINDOW = 16
RATIO_MIN, RATIO_MAX = 0.5, 3.0
SPIKE_RATIO = 1.3
SPIKE_TICKS = 4
MIN_POINTS = 4


def _applies(event: Mapping[str, Any], station: Mapping[str, Any]) -> bool:
    params = event.get("parameters") or {}
    station_ids = params.get("station_ids") or []
    region_ids = params.get("region_ids") or []
    if station_ids and station["id"] not in station_ids:
        return False
    if region_ids and station.get("region_id") not in region_ids:
        return False
    return True


def spike_events(events: Iterable[Mapping[str, Any]], station: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [e for e in events if e.get("type") == "demand_spike" and _applies(e, station)]


def _mult(event: Mapping[str, Any]) -> float:
    return float((event.get("parameters") or {}).get("multiplier", 1.5))


class MultiplierTimeline:
    """demand_multiplier of one station at any tick, derived from its current value and the event list."""

    def __init__(self, station: Mapping[str, Any], events: Iterable[Mapping[str, Any]]):
        self.spikes = spike_events(events, station)
        active_now = 1.0
        for e in self.spikes:
            if e.get("status") == "ACTIVE":
                active_now *= _mult(e)
        current = float(station.get("demand_multiplier", 1.0) or 1.0)
        self.base = current / active_now if active_now > 0 else current

    def at(self, tick: int) -> float:
        m = self.base
        for e in self.spikes:
            if e["start_tick"] <= tick < e["end_tick"]:
                m *= _mult(e)
        return m

    def upcoming(self, tick: int, horizon: int) -> Mapping[str, Any] | None:
        future = [e for e in self.spikes if e.get("status") == "SCHEDULED" and tick <= e["start_tick"] < tick + horizon]
        if not future:
            return None
        e = min(future, key=lambda x: x["start_tick"])
        return {"start_tick": e["start_tick"], "end_tick": e["end_tick"], "multiplier": _mult(e)}


def baseline_series(
    *,
    profile: str,
    fuel: str,
    region_factor: float,
    timeline: MultiplierTimeline,
    ticks: Sequence[int],
    base_time: datetime,
    base_tick: int,
    tick_minutes: float,
    fallback_per_tick: float | None = None,
) -> list[float]:
    daily = daily_liters(profile, fuel)
    tpd = ticks_per_day(tick_minutes)
    out = []
    for t in ticks:
        if daily is None:
            # Unknown profile: flat forecast from recent history; calibration keeps it honest.
            out.append(float(fallback_per_tick or 0.0))
            continue
        hour = time_at(base_time, base_tick, t, tick_minutes).hour
        out.append(daily / tpd * hour_factor(profile, hour) * region_factor * timeline.at(t))
    return out


@dataclass(frozen=True)
class Calibration:
    ratio: float
    mape: float | None
    confidence: float
    spike_by_ratio: bool
    recent_ratio: float | None
    points: int


def calibrate(actual: Sequence[float], baseline: Sequence[float], *, enabled: bool = True) -> Calibration:
    """actual/baseline are aligned, oldest first, covering at most the last CALIBRATION_WINDOW ticks."""
    pairs = [(a, b) for a, b in zip(actual, baseline, strict=False)][-CALIBRATION_WINDOW:]
    pairs = [(a, b) for a, b in pairs if b > 0]
    n = len(pairs)
    ratio = 1.0
    if enabled and n >= MIN_POINTS:
        ratio = sum(a for a, _ in pairs) / sum(b for _, b in pairs)
        ratio = min(RATIO_MAX, max(RATIO_MIN, ratio))

    errors = [abs(a - ratio * b) / a for a, b in pairs if a > 1.0]
    mape = sum(errors) / len(errors) if errors else None
    confidence = 0.5 if mape is None else max(0.0, min(1.0, 1.0 - mape))

    spike = False
    recent = None
    if enabled and n >= SPIKE_TICKS:
        last = pairs[-SPIKE_TICKS:]
        tick_ratios = [a / b for a, b in last]
        recent = sum(a for a, _ in last) / sum(b for _, b in last)
        spike = all(r > SPIKE_RATIO for r in tick_ratios)
    return Calibration(ratio=ratio, mape=mape, confidence=confidence, spike_by_ratio=spike, recent_ratio=recent, points=n)
