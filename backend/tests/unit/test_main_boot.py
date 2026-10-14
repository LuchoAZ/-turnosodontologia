"""Boot fail-fast: the process aborts with a non-zero code naming the variable (task 4.2)."""

from __future__ import annotations

import pytest
from app.config import Settings
from app.main import config_or_exit


def test_config_or_exit_returns_settings_when_complete(base_env: dict[str, str]) -> None:
    assert isinstance(config_or_exit(base_env), Settings)


def test_config_or_exit_missing_variable_exits_non_zero(
    base_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    del base_env["DATABASE_URL"]

    with pytest.raises(SystemExit) as excinfo:
        config_or_exit(base_env)

    assert excinfo.value.code != 0
    assert "DATABASE_URL" in capsys.readouterr().err


def test_config_or_exit_invalid_variable_names_reason(
    base_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    base_env["ENVIRONMENT"] = "nope"

    with pytest.raises(SystemExit):
        config_or_exit(base_env)

    err = capsys.readouterr().err
    assert "ENVIRONMENT" in err
    assert "nope" in err
