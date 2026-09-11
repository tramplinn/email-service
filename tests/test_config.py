import pytest
from pydantic import ValidationError

from email_service.config import load_settings


def test_load_settings_reads_required_and_default_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "tramplin")

    settings = load_settings()

    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_username == "tramplin"
    assert settings.smtp_port == 587
    assert settings.email_transactional_queue_name == "email-transactional"
    assert settings.email_bulk_queue_name == "email-bulk"
    assert settings.circuit_breaker_failure_threshold == 5


def test_load_settings_requires_smtp_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)

    with pytest.raises(ValidationError):
        load_settings()
