import asyncio
import logging
from collections.abc import Callable

from faststream import FastStream
from faststream.rabbit import QueueType, RabbitBroker, RabbitMessage, RabbitQueue

from email_service.circuit_breaker import CircuitBreaker, CircuitOpenError
from email_service.config import Settings, load_settings
from email_service.models import EmailJob
from email_service.smtp_client import SmtpEmailSender, SmtpSendError

logger = logging.getLogger(__name__)

# После неудачи ждём перед nack, иначе quorum-очередь тут же возвращает то же
# письмо и consumer долбит мёртвый SMTP в тесном цикле.
_SMTP_RETRY_DELAY = 2.0


def _build_queue(name: str) -> RabbitQueue:
    # Топология объявлена в infra/rabbitmq/definitions.json; declare=False —
    # сервис только подписывается, никогда не создаёт очередь сам.
    return RabbitQueue(name, queue_type=QueueType.QUORUM, durable=True, declare=False)


class EmailConsumerApplication:
    def __init__(
        self,
        settings: Settings,
        *,
        sender: SmtpEmailSender | None = None,
        breaker: CircuitBreaker | None = None,
        broker_factory: Callable[[str], RabbitBroker] = RabbitBroker,
    ) -> None:
        self.settings = settings
        self.broker = broker_factory(settings.rabbitmq_url)
        self.sender = sender or SmtpEmailSender(settings)
        self.breaker = breaker or CircuitBreaker(
            settings.circuit_breaker_failure_threshold,
            settings.circuit_breaker_reset_timeout,
        )
        self.app = FastStream(self.broker)

        self.broker.subscriber(_build_queue(settings.email_transactional_queue_name))(
            self.handle,
        )
        self.broker.subscriber(_build_queue(settings.email_bulk_queue_name))(self.handle)

    async def handle(self, job: EmailJob, message: RabbitMessage) -> None:
        try:
            await self.breaker.call(
                lambda: self.sender.send(
                    to=job.to,
                    subject=job.subject,
                    html=job.html,
                    text=job.text,
                ),
            )
        except CircuitOpenError:
            # time_until_half_open() only tracks the OPEN window's wall clock: once it
            # elapses, every message blocked behind an in-flight HALF_OPEN trial reads
            # 0.0s here too, not just the one running the trial. Without a floor those
            # nack/requeue instantly, and the queue's single consumer spins on them in
            # a tight loop for as long as the trial call is outstanding.
            delay = max(self.breaker.time_until_half_open(), _SMTP_RETRY_DELAY)
            logger.warning(
                "smtp circuit open, retrying message %s in %.1fs",
                job.message_id,
                delay,
            )
            await asyncio.sleep(delay)
            await message.nack(requeue=True)
            return
        except SmtpSendError:
            logger.exception("smtp send failed for message %s", job.message_id)
            await asyncio.sleep(_SMTP_RETRY_DELAY)
            await message.nack(requeue=True)
            return
        await message.ack()


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
