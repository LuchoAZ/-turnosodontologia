"""Typed application configuration.

The contract (see spec ``platform-runtime``) is fail-fast: the runtime validates
the whole environment at boot and refuses to start when a required variable is
missing or invalid. ``load_config`` is the single testable seam — it never reads
``os.environ`` beyond the mapping injected by the caller.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class Environment(StrEnum):
    local = "local"
    development = "development"
    test = "test"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """Environment schema.

    Field aliases are the canonical env-var names (KB ``08_arquitectura_propuesta``).
    Required variables have no default; optional ones default to ``None``.
    """

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=True,
        populate_by_name=True,
    )

    # Runtime
    environment: Environment = Field(alias="ENVIRONMENT")
    service_name: str = Field(default="odontologia-saas-api", alias="SERVICE_NAME")
    default_tenant_timezone: str = Field(
        default="America/Argentina/Buenos_Aires", alias="DEFAULT_TENANT_TIMEZONE"
    )
    apply_to_all_origins: str | None = Field(default=None, alias="APPLY_TO_ALL_ORIGINS")

    # Data stores
    database_url: str = Field(alias="DATABASE_URL")
    direct_url: str | None = Field(default=None, alias="DIRECT_URL")
    redis_url: str = Field(alias="REDIS_URL")

    # Secrets
    session_secret: str = Field(alias="SESSION_SECRET")
    jwt_refresh_secret: str = Field(alias="JWT_REFRESH_SECRET")
    kms_master_key_id: str | None = Field(default=None, alias="KMS_MASTER_KEY_ID")

    # ARCA (fiscal)
    arca_wsdl_prod_url: str | None = Field(default=None, alias="ARCA_WSDL_PROD_URL")
    arca_wsdl_test_url: str | None = Field(default=None, alias="ARCA_WSDL_TEST_URL")
    arca_cert_store_passphrase: str | None = Field(
        default=None, alias="ARCA_CERT_STORE_PASSPHRASE"
    )

    # Communications
    whatsapp_api_token: str | None = Field(default=None, alias="WHATSAPP_API_TOKEN")
    whatsapp_verify_token: str | None = Field(default=None, alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: str | None = Field(default=None, alias="WHATSAPP_APP_SECRET")
    email_provider_api_key: str | None = Field(default=None, alias="EMAIL_PROVIDER_API_KEY")

    # Object storage
    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_access_key: str | None = Field(default=None, alias="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, alias="S3_SECRET_KEY")

    # Observability
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    # Digital signature (v0.2)
    signing_provider_url: str | None = Field(default=None, alias="SIGNING_PROVIDER_URL")
    signing_provider_key: str | None = Field(default=None, alias="SIGNING_PROVIDER_KEY")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Only the injected init mapping is consulted; os.environ is never read
        # implicitly, so tests fully control the environment.
        return (init_settings,)


def env_var_names() -> set[str]:
    """Canonical env-var names declared by the schema."""
    names: set[str] = set()
    for field_name, field in Settings.model_fields.items():
        names.add(field.alias or field_name)
    return names


def load_config(env: Mapping[str, str] | None = None) -> Settings:
    """Build ``Settings`` from an injected environment mapping.

    Raises ``pydantic.ValidationError`` when a required variable is missing or
    invalid. ``env`` defaults to ``os.environ`` only when not supplied.
    """
    data: dict[str, object] = dict(os.environ if env is None else env)
    return Settings.model_validate(data)


def format_config_error(exc: ValidationError) -> str:
    """Human-readable message that names every offending variable."""
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"])
        detail = str(error["msg"])
        if "input" in error and error["type"] != "missing":
            detail = f"{detail} (got {error['input']!r})"
        parts.append(f"{location}: {detail}")
    return "invalid configuration — " + "; ".join(parts)
