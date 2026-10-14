"""Unit tests for the fail-fast configuration seam (task 4.1)."""

from __future__ import annotations

import pytest
from app.config import Environment, format_config_error, load_config
from pydantic import ValidationError


def test_load_config_with_complete_environment(base_env: dict[str, str]) -> None:
    settings = load_config(base_env)

    assert settings.environment is Environment.test
    assert settings.database_url == "postgresql://user:pass@localhost:5432/odontologia"
    assert settings.service_name == "odontologia-saas-api"


def test_load_config_missing_required_variable(base_env: dict[str, str]) -> None:
    del base_env["DATABASE_URL"]

    with pytest.raises(ValidationError) as excinfo:
        load_config(base_env)

    assert "DATABASE_URL" in format_config_error(excinfo.value)


def test_load_config_missing_other_required_variable(base_env: dict[str, str]) -> None:
    del base_env["REDIS_URL"]

    with pytest.raises(ValidationError) as excinfo:
        load_config(base_env)

    assert "REDIS_URL" in format_config_error(excinfo.value)


def test_load_config_invalid_variable(base_env: dict[str, str]) -> None:
    base_env["ENVIRONMENT"] = "not-an-environment"

    with pytest.raises(ValidationError) as excinfo:
        load_config(base_env)

    message = format_config_error(excinfo.value)
    assert "ENVIRONMENT" in message
    assert "not-an-environment" in message


def test_load_config_environment_is_case_sensitive(base_env: dict[str, str]) -> None:
    base_env["ENVIRONMENT"] = "PRODUCTION"

    with pytest.raises(ValidationError):
        load_config(base_env)
