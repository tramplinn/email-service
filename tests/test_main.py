from unittest.mock import AsyncMock, patch

import pytest

from email_service.__main__ import main


def test_main_runs_the_consumer_when_called_without_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["email-service"])
    run = AsyncMock()

    with patch("email_service.__main__.run", run):
        main()

    run.assert_awaited_once()


def test_main_exits_zero_when_healthcheck_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["email-service", "healthcheck"])

    with (
        patch("email_service.__main__.rabbitmq_is_healthy", AsyncMock(return_value=True)),
        pytest.raises(SystemExit) as excinfo,
    ):
        main()

    assert excinfo.value.code == 0


def test_main_exits_nonzero_when_healthcheck_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["email-service", "healthcheck"])

    with (
        patch("email_service.__main__.rabbitmq_is_healthy", AsyncMock(return_value=False)),
        pytest.raises(SystemExit) as excinfo,
    ):
        main()

    assert excinfo.value.code == 1


def test_main_rejects_unknown_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["email-service", "bogus"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert "usage" in str(excinfo.value)
