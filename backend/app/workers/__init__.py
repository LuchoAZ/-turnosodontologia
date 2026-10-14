"""Celery worker entrypoint (skeleton — no tasks yet).

Started with ``celery -A app.workers worker``. The concrete ARCA/comms/PDF tasks
land in later changes; C-01 only needs the app to boot.
"""

from __future__ import annotations

import os
import sys

from celery import Celery

broker_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery("odontologia", broker=broker_url, backend=broker_url)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=os.environ.get("DEFAULT_TENANT_TIMEZONE", "UTC"),
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# The prefork pool is unsupported on Windows (billiard spawns children that fail
# with PermissionError). Use the solo pool locally; Linux/Docker keep prefork.
if sys.platform == "win32":
    app.conf.worker_pool = "solo"

