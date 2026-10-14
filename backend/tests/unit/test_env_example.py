"""Documentation guard: every schema env var must be in .env.example (tasks 3.2/3.3)."""

from __future__ import annotations

from pathlib import Path

from app.config import env_var_names

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def _documented_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_documents_every_schema_variable() -> None:
    documented = _documented_keys(ENV_EXAMPLE.read_text(encoding="utf-8"))

    missing = env_var_names() - documented

    assert missing == set(), f"env vars missing from .env.example: {sorted(missing)}"
