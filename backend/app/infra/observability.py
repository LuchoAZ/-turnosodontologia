"""Shared observability bootstrap (OpenTelemetry + Sentry) with degraded mode.

The runtime must never fail to start because a tracing exporter or an error DSN
is absent: in that case it boots in ``degraded`` mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import sentry_sdk
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import Settings


class Status(StrEnum):
    configured = "configured"
    degraded = "degraded"


@dataclass(frozen=True)
class ObservabilityState:
    tracing: Status
    error_tracking: Status


def setup_observability(
    settings: Settings, *, tracer_provider: TracerProvider | None = None
) -> ObservabilityState:
    """Initialize tracing and error tracking, returning the resulting state."""
    return ObservabilityState(
        tracing=_setup_tracing(settings, tracer_provider),
        error_tracking=_setup_error_tracking(settings),
    )


def _setup_tracing(settings: Settings, provider: TracerProvider | None) -> Status:
    resolved = provider or TracerProvider(
        resource=Resource.create({SERVICE_NAME: settings.service_name})
    )
    status = Status.degraded
    if settings.otel_exporter_otlp_endpoint:
        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
        resolved.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        status = Status.configured
    trace.set_tracer_provider(resolved)
    return status


def _setup_error_tracking(settings: Settings) -> Status:
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.0)
        return Status.configured
    return Status.degraded


def get_tracer(name: str) -> trace.Tracer:
    """Tracer accessor that later changes enrich with domain correlation."""
    return trace.get_tracer(name)
