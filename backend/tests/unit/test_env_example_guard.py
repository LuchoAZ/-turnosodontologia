from __future__ import annotations

import re
from pathlib import Path

from app.config import env_var_names


def test_env_example_documents_all_schema_vars() -> None:
    """3.2/3.3 guard: .env.example must document every variable declared by the schema."""
    root = Path(__file__).resolve().parents[3]
    env_example_path = root / ".env.example"
    assert env_example_path.exists(), f"{env_example_path} does not exist"
    content = env_example_path.read_text(encoding="utf-8")
    declared = {
        match.group(1)
        for match in re.finditer(r"^([A-Z][A-Z0-9_]+)=", content, flags=re.MULTILINE)
    }
    missing = sorted(env_var_names() - declared)
    assert not missing, "Missing: " + ", ".join(missing)
    extra = sorted(declared - env_var_names())
    assert not extra, "Undocumented/stray: " + ", ".join(extra)
