import asyncio
from collections.abc import Callable

from faststream import FastStream
from faststream.rabbit import QueueType, RabbitBroker, RabbitQueue

from email_service.circuit_breaker import CircuitBreaker
from email_service.config import Settings, load_settings
from email_service.delivery import EmailDeliveryHandler
from email_service.smtp_client import EmailSender, SmtpEmailSender


def _build_queue(name: str) -> RabbitQueue:
    return RabbitQueue(name, queue_type=QueueType.QUORUM, durable=True, declare=False)


class EmailConsumerApplication:
    """Композиционный корень: собирает брокер, очереди и обработчик доставки.
    Сама политика ретраев и брейкера — в EmailDeliveryHandler."""

    def __init__(
        self,
        settings: Settings,
        *,
        sender: EmailSender | None = None,
        breaker: CircuitBreaker | None = None,
        broker_factory: Callable[[str], RabbitBroker] = RabbitBroker,
    ) -> None:
        self.settings = settings
        self.broker = broker_factory(settings.rabbitmq_url)
        self.delivery = EmailDeliveryHandler(
            sender or SmtpEmailSender(settings),
            breaker
            or CircuitBreaker(
                settings.circuit_breaker_failure_threshold,
                settings.circuit_breaker_reset_timeout,
            ),
        )
        self.app = FastStream(self.broker)

        self.broker.subscriber(_build_queue(settings.email_transactional_queue_name))(
            self.delivery.handle,
        )
        self.broker.subscriber(_build_queue(settings.email_bulk_queue_name))(self.delivery.handle)


def create_consumer(settings: Settings | None = None) -> EmailConsumerApplication:
    return EmailConsumerApplication(settings or load_settings())


async def run() -> None:
    await create_consumer().app.run()


async def rabbitmq_is_healthy(settings: Settings | None = None) -> bool:
    settings = settings or load_settings()
    broker = RabbitBroker(settings.rabbitmq_url)
    try:
        await asyncio.wait_for(broker.connect(), timeout=3)
        return await broker.ping(timeout=2)
    except Exception:
        return False
    finally:
        await broker.stop()
