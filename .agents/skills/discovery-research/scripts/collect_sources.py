#!/usr/bin/env python3
"""Lee las notas de competidores escritas por web-scraper en
discovery/sources/*.md (esquema fijo: ver web-scraper/references/output-schema.md)
y arma una tabla comparativa rápida, para no tener que releer cada nota a mano
durante la ronda de preguntas de la Fase 2.

Uso:
    python collect_sources.py [directorio_discovery]
    # por defecto usa ./discovery

Imprime una tabla markdown por stdout. Si una nota no tiene alguna sección
esperada, la deja como "(no encontrado)" en vez de fallar — las notas son
texto libre escrito por un agente, no un formato estrictamente parseable.
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SECTIONS = {
    "Problema que resuelve": "problema",
    "Pricing": "pricing",
    "Diferenciadores": "diferenciadores",
}


def extract_title(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else "(sin nombre)"


def extract_section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not match:
        return "(no encontrado)"
    body = match.group(1).strip()
    body = re.sub(r"\s+", " ", body)
    return (body[:117] + "...") if len(body) > 120 else (body or "(no encontrado)")


def main() -> None:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("discovery")
    sources_dir = base / "sources"

    if not sources_dir.is_dir():
        print(f"(no hay notas en {sources_dir} todavia)")
        return

    notes = sorted(sources_dir.glob("*.md"))
    if not notes:
        print(f"(no hay notas .md en {sources_dir} todavia)")
        return

    headers = ["Competidor"] + list(SECTIONS.keys())
    rows = []
    for note_path in notes:
        text = note_path.read_text(encoding="utf-8")
        row = [extract_title(text)]
        for heading in SECTIONS:
            row.append(extract_section(text, heading))
        rows.append(row)

    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        print("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")


if __name__ == "__main__":
    main()
