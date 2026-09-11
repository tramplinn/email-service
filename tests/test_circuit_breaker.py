import asyncio

import pytest

from email_service.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


async def _ok() -> str:
    return "ok"


async def _fail() -> str:
    raise RuntimeError("boom")


async def test_stays_closed_while_calls_succeed() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=10)

    for _ in range(5):
        assert await breaker.call(_ok) == "ok"

    assert breaker.state == CircuitState.CLOSED


async def test_opens_after_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=10)

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    state_after_first_failure = breaker.state
    assert state_after_first_failure == CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    state_after_second_failure = breaker.state
    assert state_after_second_failure == CircuitState.OPEN


async def test_open_breaker_rejects_calls_without_invoking_action() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=10)

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)

    called = False

    async def action() -> None:
        nonlocal called
        called = True

    with pytest.raises(CircuitOpenError):
        await breaker.call(action)
    assert called is False


async def test_half_open_trial_succeeds_and_closes() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    state_after_failure = breaker.state
    assert state_after_failure == CircuitState.OPEN

    await asyncio.sleep(0.02)

    assert await breaker.call(_ok) == "ok"
    state_after_trial = breaker.state
    assert state_after_trial == CircuitState.CLOSED


async def test_half_open_trial_failure_reopens() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    await asyncio.sleep(0.02)

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    assert breaker.state == CircuitState.OPEN


async def test_half_open_allows_only_one_trial_at_a_time() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)

    with pytest.raises(RuntimeError):
        await breaker.call(_fail)
    await asyncio.sleep(0.02)

    release = asyncio.Event()

    async def slow_trial() -> str:
        await release.wait()
        return "ok"

    trial_task = asyncio.create_task(breaker.call(slow_trial))
    await asyncio.sleep(0)  # let the trial mark itself in-flight

    with pytest.raises(CircuitOpenError):
        await breaker.call(_ok)

    release.set()
    assert await trial_task == "ok"
    assert breaker.state == CircuitState.CLOSED


def test_time_until_half_open_is_zero_when_never_opened() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=10)
    assert breaker.time_until_half_open() == 0.0
