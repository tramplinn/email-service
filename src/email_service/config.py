from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Своих клиентов приложения тут нет: очередь и SMTP — единственные зависимости."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    rabbitmq_url: str = "amqp://tramplin:tramplin@localhost:5672/"
    email_transactional_queue_name: str = "email-transactional"
    email_bulk_queue_name: str = "email-bulk"

    smtp_host: str
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_start_tls: bool = True
    smtp_from_address: str = "noreply@tramplin.example"
    smtp_timeout: float = 10.0

    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: float = 30.0


def load_settings() -> Settings:
    return Settings()
