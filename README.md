# Tramplin Email Service

Takes email jobs from RabbitMQ and sends them over SMTP. It doesn't render
templates or touch the database — the backend sends a ready `subject`, `html`,
and `text`.

Stack: Python 3.14, FastStream, aiosmtplib, Pydantic Settings, uv.

## How it works

```text
backend → RabbitMQ ─┬─ <prefix>-email-transactional ─┐
                    └─ <prefix>-email-bulk ──────────┴→ email-service → SMTP
```

- Two queues: transactional (sign-in codes and such) and bulk. They are declared in
  [`infra`](https://gitlab.com/tramplin1/infra/-/blob/main/rabbitmq/definitions.json);
  the service only subscribes.
- Each message is an [`EmailJob`](src/email_service/models.py): `message_id`,
  `category`, `to`, `subject`, `html`, `text`.
- Sent → `ack`. SMTP error → back to the queue after a pause.
- After `CIRCUIT_BREAKER_FAILURE_THRESHOLD` failures in a row, the circuit breaker
  stops sending for `CIRCUIT_BREAKER_RESET_TIMEOUT` seconds, then tries one email
  to see if SMTP is back.

## Quick start

You need Python 3.14, [uv](https://docs.astral.sh/uv/), and a running RabbitMQ
(for example, from `infra`).

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

To catch emails locally, use any SMTP catcher, like
[Mailpit](https://mailpit.axllent.org/) on port `1025`.

### With Docker

The container is read-only, runs as a non-root user, and joins the
`tramplin-edge` network where RabbitMQ lives:

```bash
cp .env.example .env.runtime
make staging-config
make staging-up
```

## Commands

```bash
make run           # start the worker
make healthcheck   # check the RabbitMQ connection
make check         # Ruff, mypy, pytest
make format        # format and autofix
make lock          # update uv.lock
```

Test coverage must stay at 90% or higher.

## Structure

```text
src/email_service/
  __main__.py         entry point: worker or healthcheck
  app.py              broker, queues, subscribers
  delivery.py         ack/nack/retry for one message
  circuit_breaker.py  circuit breaker
  smtp_client.py      SMTP sending
  models.py           EmailJob schema
  config.py           settings
tests/                unit tests
```
