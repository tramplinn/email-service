import asyncio
import sys

from email_service.consumer import create_consumer, rabbitmq_is_healthy


def main() -> None:
    if not sys.argv[1:]:
        asyncio.run(run())
        return
    if sys.argv[1:] == ["healthcheck"]:
        raise SystemExit(0 if asyncio.run(rabbitmq_is_healthy()) else 1)
    raise SystemExit("usage: python -m email_service [healthcheck]")


async def run() -> None:
    await create_consumer().app.run()


if __name__ == "__main__":
    main()
