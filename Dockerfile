FROM python:3.14.7-alpine3.23

RUN apk update && apk upgrade --no-cache

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-cache \
    && PIP_ROOT_USER_ACTION=ignore /usr/local/bin/python -m pip uninstall -y pip \
    && rm -f /usr/local/bin/uv

RUN adduser -D -u 10001 -s /sbin/nologin appuser
USER appuser

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-m", "email_service", "healthcheck"]

CMD ["python", "-m", "email_service"]
