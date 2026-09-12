from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from email_service.circuit_breaker import CircuitBreaker
from email_service.delivery import _SMTP_RETRY_DELAY, EmailDeliveryHandler
from email_service.models import EmailJob
from email_service.smtp_client import SmtpSendError


def _job() -> EmailJob:
    return EmailJob(
        message_id=uuid4(),
        category="auth_otp",
        to="student@example.com",
        subject="Hi",
        html="<p>hi</p>",
        text="hi",
    )


def _handler(sender: object, breaker: CircuitBreaker | None = None) -> EmailDeliveryHandler:
    return EmailDeliveryHandler(sender, breaker or CircuitBreaker(5, 30.0))  # type: ignore[arg-type]


async def test_handle_acks_after_a_successful_send() -> None:
    sender = Mock(send=AsyncMock())
    handler = _handler(sender)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    await handler.handle(_job(), message)

    sender.send.assert_awaited_once()
    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_handle_requeues_on_smtp_failure() -> None:
    sender = Mock(send=AsyncMock(side_effect=SmtpSendError("refused")))
    handler = _handler(sender)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    with patch("email_service.delivery.asyncio.sleep", new=AsyncMock()) as sleep:
        await handler.handle(_job(), message)

    sleep.assert_awaited_once()
    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_called()


async def test_handle_requeues_after_backing_off_when_circuit_is_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=1000)
    sender = Mock(send=AsyncMock(side_effect=SmtpSendError("refused")))
    handler = _handler(sender, breaker)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    # первая попытка открывает брейкер и сама отправляет письмо
    with patch("email_service.delivery.asyncio.sleep", new=AsyncMock()):
        await handler.handle(_job(), message)
    assert sender.send.await_count == 1

    # вторая попытка бьётся об открытый брейкер, SMTP не трогается
    with patch("email_service.delivery.asyncio.sleep", new=AsyncMock()) as sleep:
        await handler.handle(_job(), message)

    assert sender.send.await_count == 1
    sleep.assert_awaited_once()
    assert sleep.await_args is not None
    assert sleep.await_args.args[0] == pytest.approx(1000, abs=1)
    assert message.nack.await_count == 2
    message.nack.assert_awaited_with(requeue=True)


async def test_handle_floors_retry_delay_behind_an_in_flight_half_open_trial() -> None:
    """Once reset_timeout has elapsed, time_until_half_open() reads 0.0 for every caller,
    including one blocked behind an already-running HALF_OPEN trial — not just the trial
    itself. Regression for the busy nack/requeue loop this used to cause
    (see EmailDeliveryHandler.handle)."""
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=0)
    sender = Mock(send=AsyncMock(side_effect=SmtpSendError("refused")))
    handler = _handler(sender, breaker)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    # Открывает брейкер; reset_timeout=0, так что он сразу же проходим для следующего вызова.
    with patch("email_service.delivery.asyncio.sleep", new=AsyncMock()):
        await handler.handle(_job(), message)

    # Имитируем пробный HALF_OPEN вызов, который ещё не завершился.
    breaker._state = breaker._state.HALF_OPEN
    breaker._trial_in_flight = True

    with patch("email_service.delivery.asyncio.sleep", new=AsyncMock()) as sleep:
        await handler.handle(_job(), message)

    assert sleep.await_args is not None
    assert sleep.await_args.args[0] == pytest.approx(_SMTP_RETRY_DELAY)
