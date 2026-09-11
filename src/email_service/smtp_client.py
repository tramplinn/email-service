from email.message import EmailMessage

import aiosmtplib

from email_service.config import Settings


class SmtpSendError(Exception):
    pass


class SmtpEmailSender:
    """Новое соединение на письмо: сервис синхронно консьюмит очередь, пул
    соединений здесь не отбивает задержку, а только усложняет отладку."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, *, to: str, subject: str, html: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username or None,
                password=self._settings.smtp_password.get_secret_value() or None,
                start_tls=self._settings.smtp_start_tls,
                timeout=self._settings.smtp_timeout,
            )
        except (aiosmtplib.SMTPException, TimeoutError, OSError) as error:
            raise SmtpSendError(str(error)) from error
