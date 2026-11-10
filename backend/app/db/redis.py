"""Cliente Redis de la aplicación (design D5/D11) — usado solo por MFA."""

from __future__ import annotations

from fastapi import Request
from redis import Redis

from app.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_redis(request: Request) -> Redis:
    client: Redis = request.app.state.redis
    return client
