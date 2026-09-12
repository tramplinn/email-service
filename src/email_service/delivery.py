import asyncio
import logging

from faststream.rabbit import RabbitMessage

from email_service.circuit_breaker import CircuitBreaker, CircuitOpenError
from email_service.models import EmailJob
from email_service.smtp_client import EmailSender, SmtpSendError

logger = logging.getLogger(__name__)

_SMTP_RETRY_DELAY = 2.0


class EmailDeliveryHandler:
    """Решает судьбу одного сообщения: отправить, дать брейкеру отказать
    сразу или откатить в очередь с задержкой. Подписку и брокер собирает
    app.py — здесь только политика доставки одного job'а."""

    def __init__(self, sender: EmailSender, breaker: CircuitBreaker) -> None:
        self._sender = sender
        self._breaker = breaker

    async def handle(self, job: EmailJob, message: RabbitMessage) -> None:
        try:
            await self._breaker.call(
                lambda: self._sender.send(
                    to=job.to,
                    subject=job.subject,
                    html=job.html,
                    text=job.text,
                ),
            )
        except CircuitOpenError:
            delay = max(self._breaker.time_until_half_open(), _SMTP_RETRY_DELAY)
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
