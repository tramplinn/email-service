# Tramplin Email Service

Независимый воркер доставки писем: читает задания из RabbitMQ и отправляет их
через SMTP. Сервис не знает о шаблонах и не ходит в базу — готовые `subject`,
`html` и `text` формирует backend.

Стек: Python 3.14, FastStream (RabbitMQ), aiosmtplib, Pydantic Settings и uv.

## Как это работает

```text
backend → RabbitMQ ─┬─ <prefix>-email-transactional ─┐
                    └─ <prefix>-email-bulk ──────────┴→ email-service → SMTP
```

- Слушает две quorum-очереди: транзакционные письма (коды входа и т.п.) и
  массовые рассылки. Очереди объявлены в репозитории
  [`infra`](https://gitlab.com/tramplin1/infra/-/blob/main/rabbitmq/definitions.json);
  сервис подписывается с `declare=False` и сам их не создаёт.
- Сообщение — JSON [`EmailJob`](src/email_service/models.py):
  `message_id`, `category`, `to`, `subject`, `html`, `text`.
- Успешная отправка → `ack`. Ошибка SMTP → `nack(requeue=True)` с паузой.
- Circuit breaker защищает SMTP-сервер: после
  `CIRCUIT_BREAKER_FAILURE_THRESHOLD` ошибок подряд попытки прекращаются на
  `CIRCUIT_BREAKER_RESET_TIMEOUT` секунд, сообщения возвращаются в очередь, а
  затем одна пробная отправка решает, закрывать ли брейкер.

## Быстрый старт

Нужны Python `>=3.14,<3.15`, [uv](https://docs.astral.sh/uv/) и доступный
RabbitMQ (например, из репозитория `infra`).

```bash
make install
cat > .env <<'ENV'
RABBITMQ_URL=amqp://tramplin:tramplin@localhost:5672/
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_START_TLS=false
ENV
make run
```

Для локальной проверки подойдёт любой SMTP-перехватчик, например
[Mailpit](https://mailpit.axllent.org/) на порту `1025`.

## Команды

```bash
make run           # запустить воркер
make healthcheck   # проверить соединение с RabbitMQ (exit code 0/1)
make check         # Ruff, mypy и pytest
make format        # автоформатирование и автофиксы Ruff
make lock          # обновить uv.lock
```

Тестовое покрытие должно быть не ниже 90%.

## Конфигурация

Настройки читаются из переменных окружения или `.env`; полный список — в
[`src/email_service/config.py`](src/email_service/config.py), шаблон для
деплоя — [`.env.example`](.env.example).

| Переменная                          | По умолчанию                          | Назначение                         |
| ----------------------------------- | ------------------------------------- | ---------------------------------- |
| `RABBITMQ_URL`                      | `amqp://tramplin:tramplin@localhost:5672/` | подключение к брокеру         |
| `EMAIL_TRANSACTIONAL_QUEUE_NAME`    | `email-transactional`                 | очередь транзакционных писем       |
| `EMAIL_BULK_QUEUE_NAME`             | `email-bulk`                          | очередь массовых рассылок          |
| `SMTP_HOST`                         | — (обязательна)                       | SMTP-сервер                        |
| `SMTP_PORT`                         | `587`                                 | порт SMTP                          |
| `SMTP_USERNAME`, `SMTP_PASSWORD`    | пусто                                 | учётные данные SMTP                |
| `SMTP_START_TLS`                    | `true`                                | STARTTLS                           |
| `SMTP_FROM_ADDRESS`                 | `noreply@tramplin.example`            | адрес отправителя                  |
| `SMTP_TIMEOUT`                      | `10.0`                                | таймаут SMTP, секунды              |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5`                                   | ошибок подряд до размыкания        |
| `CIRCUIT_BREAKER_RESET_TIMEOUT`     | `30.0`                                | пауза перед пробной отправкой, с   |

В Compose имена очередей собираются из `QUEUE_ENV_PREFIX`
(`tramplin-stage`, `tramplin-prod`), а `RABBITMQ_URL` — из `RABBITMQ_USER` и
`RABBITMQ_PASSWORD`.

## Структура

```text
src/email_service/
  __main__.py         точка входа: воркер или healthcheck
  app.py              композиционный корень: брокер, очереди, подписчики
  delivery.py         политика доставки одного сообщения (ack/nack/retry)
  circuit_breaker.py  circuit breaker для SMTP
  smtp_client.py      отправка через aiosmtplib
  models.py           схема сообщения EmailJob
  config.py           настройки
tests/                unit-тесты
```

## Docker

[`docker-compose.yml`](docker-compose.yml) запускает воркер в read-only
контейнере от непривилегированного пользователя и подключает его к внешней сети
`tramplin-edge`, где живёт RabbitMQ из `infra`.

```bash
cp .env.example .env.runtime
make staging-config
make staging-up
```

## CI/CD

Pipeline проверяет Compose-конфигурацию, запускает Ruff, mypy и pytest с
покрытием, сканирует секреты и зависимости (gitleaks, Semgrep, Trivy), собирает
immutable-образ и разворачивает его: ветка `stage` — в Compose-проект
`tramplin-email-stage`, `main` — в production.

Нужные protected CI/CD variables:

- `SERVER_IP`, `SSH_PORT`, `SSH_USER`, `SSH_PRIVATE_KEY`
- `STAGE_ENV`, `PROD_ENV` типа File
