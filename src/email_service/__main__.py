import asyncio
import sys

from email_service.app import rabbitmq_is_healthy, run


def main() -> None:
    if not sys.argv[1:]:
        asyncio.run(run())
        return
    if sys.argv[1:] == ["healthcheck"]:
        raise SystemExit(0 if asyncio.run(rabbitmq_is_healthy()) else 1)
    raise SystemExit("usage: python -m email_service [healthcheck]")


if __name__ == "__main__":
    main()
