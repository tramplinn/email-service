import time
from collections.abc import Awaitable, Callable
from enum import Enum, auto
from typing import TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitOpenError(Exception):
    """SMTP не тронут: брейкер отказал сам, до истечения reset_timeout."""


class CircuitBreaker:
    """Половинчатое открытие не параллелится: пока пробный вызов не завершился,
    остальные вызовы отражаются как OPEN — иначе шторм запросов бьёт по едва
    ожившему SMTP тем же числом соединений, что и уронило его."""

    def __init__(self, failure_threshold: int, reset_timeout: float) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False

    @property
    def state(self) -> CircuitState:
        return self._state

    def time_until_half_open(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self._reset_timeout - (time.monotonic() - self._opened_at))

    async def call(self, action: Callable[[], Awaitable[T]]) -> T:
        if not self._may_attempt():
            raise CircuitOpenError
        try:
            result = await action()
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _may_attempt(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self.time_until_half_open() > 0:
                return False
            self._state = CircuitState.HALF_OPEN
            self._trial_in_flight = False
        if self._trial_in_flight:
            return False
        self._trial_in_flight = True
        return True

    def _on_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def _on_failure(self) -> None:
        self._trial_in_flight = False
        if self._state == CircuitState.HALF_OPEN:
            self._open()
            return
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
