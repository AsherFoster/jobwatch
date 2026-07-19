"""Shared backoff state for rate-limited LLM calls.

The worker holds one RateLimitGate per LLM client. When a task hits a rate
limit it closes the gate until the provider's stated reset time; every other
task checks the gate first and snoozes without burning an API call. The gate
is in-process state, which is enough while the worker runs as a single
process.

Snooze delays get random jitter on top of the wait so that a backlog of
snoozed jobs drains gradually once the limit resets, rather than stampeding
the API the moment it reopens.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

MIN_JITTER = 30.0


class RateLimitGate:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._reopen_at = 0.0

    def close_for(self, seconds: float) -> None:
        self._reopen_at = max(self._reopen_at, self._clock() + seconds)

    def seconds_until_open(self) -> float:
        return max(0.0, self._reopen_at - self._clock())


def backoff_delay(wait: float) -> float:
    """wait plus jitter — an extra uniform 0..max(MIN_JITTER, wait/2) seconds.

    Proportional jitter spreads a long (e.g. daily-quota) backlog over a
    proportionally wider window; the floor keeps short waits from bunching up.
    """
    return wait + random.uniform(0, max(MIN_JITTER, wait / 2))
