from __future__ import annotations

import time
from collections.abc import Callable

from app.metrics import BREAKER_STATE

CLOSED, HALF_OPEN, OPEN = "closed", "half_open", "open"
_GAUGE = {CLOSED: 0, HALF_OPEN: 1, OPEN: 2}


class CircuitBreaker:
    """Opens after `threshold` consecutive failures; half-opens after `reset_after` seconds.

    In half-open state one trial call is let through: success closes the breaker, failure re-opens it.
    """

    def __init__(self, threshold: int = 5, reset_after: float = 10.0, clock: Callable[[], float] = time.monotonic):
        self.threshold = threshold
        self.reset_after = reset_after
        self.clock = clock
        self.failures = 0
        self._state = CLOSED
        self.opened_at: float | None = None
        self._trial_in_flight = False
        BREAKER_STATE.set(0)

    @property
    def state(self) -> str:
        if self._state == OPEN and self.opened_at is not None and self.clock() - self.opened_at >= self.reset_after:
            self._set(HALF_OPEN)
            self._trial_in_flight = False
        return self._state

    def allow(self) -> bool:
        state = self.state
        if state == CLOSED:
            return True
        if state == HALF_OPEN and not self._trial_in_flight:
            self._trial_in_flight = True
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self._trial_in_flight = False
        self._set(CLOSED)

    def failure(self) -> None:
        self.failures += 1
        self._trial_in_flight = False
        if self._state == HALF_OPEN or self.failures >= self.threshold:
            self._set(OPEN)
            self.opened_at = self.clock()

    def _set(self, state: str) -> None:
        self._state = state
        BREAKER_STATE.set(_GAUGE[state])
