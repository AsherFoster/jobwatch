from __future__ import annotations

from jobwatch.rate_limit import MIN_JITTER, RateLimitGate, backoff_delay


def gate_at(now: float) -> tuple[RateLimitGate, list[float]]:
    """Gate on a fake clock; mutate the returned list's element to advance time."""
    clock = [now]
    return RateLimitGate(clock=lambda: clock[0]), clock


def test_gate_starts_open():
    gate, _ = gate_at(100.0)
    assert gate.seconds_until_open() == 0.0


def test_closed_gate_reopens_when_time_passes():
    gate, clock = gate_at(100.0)
    gate.close_for(40.0)

    assert gate.seconds_until_open() == 40.0
    clock[0] = 125.0
    assert gate.seconds_until_open() == 15.0
    clock[0] = 141.0
    assert gate.seconds_until_open() == 0.0


def test_close_for_never_shortens_an_existing_close():
    gate, _ = gate_at(100.0)
    gate.close_for(60.0)
    gate.close_for(10.0)

    assert gate.seconds_until_open() == 60.0


def test_backoff_delay_adds_bounded_jitter():
    for _ in range(100):
        assert 10.0 <= backoff_delay(10.0) <= 10.0 + MIN_JITTER

    # Long waits get proportionally more spread than MIN_JITTER.
    for _ in range(100):
        assert 3600.0 <= backoff_delay(3600.0) <= 3600.0 + 1800.0
