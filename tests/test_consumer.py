from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from faststream.rabbit import RabbitBroker

from email_service.circuit_breaker import CircuitBreaker
from email_service.config import Settings
from email_service.consumer import (
    EmailConsumerApplication,
    create_consumer,
    rabbitmq_is_healthy,
    run,
)
from email_service.models import EmailJob
from email_service.smtp_client import SmtpSendError


def _settings() -> Settings:
    return Settings(smtp_host="smtp.example.com")


def _job() -> EmailJob:
    return EmailJob(
        message_id=uuid4(),
        category="auth_otp",
        to="student@example.com",
        subject="Hi",
        html="<p>hi</p>",
        text="hi",
    )


def _app(**kwargs: object) -> EmailConsumerApplication:
    return EmailConsumerApplication(_settings(), broker_factory=Mock(), **kwargs)  # type: ignore[arg-type]


async def test_handle_acks_after_a_successful_send() -> None:
    sender = Mock(send=AsyncMock())
    app = _app(sender=sender)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    await app.handle(_job(), message)

    sender.send.assert_awaited_once()
    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_handle_requeues_on_smtp_failure() -> None:
    sender = Mock(send=AsyncMock(side_effect=SmtpSendError("refused")))
    app = _app(sender=sender)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    with patch("email_service.consumer.asyncio.sleep", new=AsyncMock()) as sleep:
        await app.handle(_job(), message)

    sleep.assert_awaited_once()
    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_called()


async def test_handle_requeues_after_backing_off_when_circuit_is_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=1000)
    sender = Mock(send=AsyncMock(side_effect=SmtpSendError("refused")))
    app = _app(sender=sender, breaker=breaker)
    message = Mock(ack=AsyncMock(), nack=AsyncMock())

    # первая попытка открывает брейкер и сама отправляет письмо
    with patch("email_service.consumer.asyncio.sleep", new=AsyncMock()):
        await app.handle(_job(), message)
    assert sender.send.await_count == 1

    # вторая попытка бьётся об открытый брейкер, SMTP не трогается
    with patch("email_service.consumer.asyncio.sleep", new=AsyncMock()) as sleep:
        await app.handle(_job(), message)

    assert sender.send.await_count == 1
    sleep.assert_awaited_once()
    assert sleep.await_args is not None
    assert sleep.await_args.args[0] == pytest.approx(1000, abs=1)
    assert message.nack.await_count == 2
    message.nack.assert_awaited_with(requeue=True)


def test_subscribes_to_both_configured_queues() -> None:
    broker = Mock()
    broker.subscriber = Mock(return_value=lambda handler: handler)
    broker_factory = Mock(return_value=broker)

    consumer = EmailConsumerApplication(
        Settings(
            smtp_host="smtp.example.com",
            email_transactional_queue_name="tx",
            email_bulk_queue_name="bulk",
        ),
        broker_factory=broker_factory,
    )

    assert broker.subscriber.call_count == 2
    subscribed_names = {call.args[0].name for call in broker.subscriber.call_args_list}
    assert subscribed_names == {"tx", "bulk"}
    assert consumer.app.broker is broker


def test_create_consumer_builds_against_a_real_broker() -> None:
    consumer = create_consumer(Settings(smtp_host="smtp.example.com"))

    assert isinstance(consumer.broker, RabbitBroker)


async def test_run_starts_the_consumer_apps_faststream_loop() -> None:
    fake_app = Mock(run=AsyncMock())
    fake_consumer = Mock(app=fake_app)

    with patch("email_service.consumer.create_consumer", return_value=fake_consumer):
        await run()

    fake_app.run.assert_awaited_once()


async def test_rabbitmq_is_healthy_returns_true_when_ping_succeeds() -> None:
    broker = Mock(connect=AsyncMock(), ping=AsyncMock(return_value=True), stop=AsyncMock())

    with patch("email_service.consumer.RabbitBroker", return_value=broker):
        assert await rabbitmq_is_healthy(_settings()) is True

    broker.stop.assert_awaited_once()


async def test_rabbitmq_is_healthy_returns_false_when_connect_fails() -> None:
    broker = Mock(
        connect=AsyncMock(side_effect=ConnectionError("refused")),
        ping=AsyncMock(),
        stop=AsyncMock(),
    )

    with patch("email_service.consumer.RabbitBroker", return_value=broker):
        assert await rabbitmq_is_healthy(_settings()) is False

    broker.stop.assert_awaited_once()
