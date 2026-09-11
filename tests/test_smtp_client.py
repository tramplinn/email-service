from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest

from email_service.config import Settings
from email_service.smtp_client import SmtpEmailSender, SmtpSendError


def _settings(**overrides: object) -> Settings:
    return Settings(smtp_host="smtp.example.com", **overrides)  # type: ignore[arg-type]


async def test_send_delivers_message_with_configured_credentials() -> None:
    settings = _settings(
        smtp_port=2525,
        smtp_username="tramplin",
        smtp_password="secret",  # noqa: S106 - test fixture value, not a real credential
        smtp_from_address="noreply@tramplin.dev",
        smtp_timeout=5.0,
    )
    sender = SmtpEmailSender(settings)

    with patch("email_service.smtp_client.aiosmtplib.send", new=AsyncMock()) as send:
        await sender.send(to="student@example.com", subject="Hi", html="<p>hi</p>", text="hi")

    assert send.await_count == 1
    assert send.await_args is not None
    message, kwargs = send.await_args.args[0], send.await_args.kwargs
    assert message["From"] == "noreply@tramplin.dev"
    assert message["To"] == "student@example.com"
    assert message["Subject"] == "Hi"
    assert kwargs == {
        "hostname": "smtp.example.com",
        "port": 2525,
        "username": "tramplin",
        "password": "secret",
        "start_tls": True,
        "timeout": 5.0,
    }


async def test_send_omits_credentials_when_not_configured() -> None:
    sender = SmtpEmailSender(_settings())

    with patch("email_service.smtp_client.aiosmtplib.send", new=AsyncMock()) as send:
        await sender.send(to="student@example.com", subject="Hi", html="<p>hi</p>", text="hi")

    assert send.await_args is not None
    assert send.await_args.kwargs["username"] is None
    assert send.await_args.kwargs["password"] is None


@pytest.mark.parametrize(
    "error",
    [aiosmtplib.SMTPException("refused"), TimeoutError(), OSError("unreachable")],
)
async def test_send_wraps_transport_errors(error: Exception) -> None:
    sender = SmtpEmailSender(_settings())

    with (
        patch("email_service.smtp_client.aiosmtplib.send", new=AsyncMock(side_effect=error)),
        pytest.raises(SmtpSendError),
    ):
        await sender.send(to="student@example.com", subject="Hi", html="<p>hi</p>", text="hi")
