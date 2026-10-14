"""Observability bootstrap contract: configured/degraded + tracer init (task 4.7)."""

from __future__ import annotations

import sentry_sdk
from app.config import load_config
from app.infra.observability import Status, get_tracer, setup_observability
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider


def test_tracing_configured_when_exporter_present(base_env: dict[str, str]) -> None:
    settings = load_config({**base_env, "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4318"})

    state = setup_observability(settings)

    assert state.tracing is Status.configured


def test_tracing_degraded_without_exporter(base_env: dict[str, str]) -> None:
    settings = load_config(base_env)

    state = setup_observability(settings)

    assert state.tracing is Status.degraded


def test_tracer_is_initialized_without_a_real_backend(base_env: dict[str, str]) -> None:
    settings = load_config(base_env)
    provider = TracerProvider()

    setup_observability(settings, tracer_provider=provider)

    assert isinstance(trace.get_tracer_provider(), TracerProvider)
    assert get_tracer(__name__) is not None


def test_error_tracking_configured_with_dsn(base_env: dict[str, str]) -> None:
    settings = load_config({**base_env, "SENTRY_DSN": "https://public@example.com/1"})

    state = setup_observability(settings)

    assert state.error_tracking is Status.configured
    assert sentry_sdk.get_client().dsn is not None
    sentry_sdk.get_client().close()


def test_error_tracking_degraded_without_dsn(base_env: dict[str, str]) -> None:
    settings = load_config(base_env)

    state = setup_observability(settings)

    assert state.error_tracking is Status.degraded
