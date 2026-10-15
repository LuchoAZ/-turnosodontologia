# State Contract — kb-creator owns `state.kb`

Reference: C-13a frozen contract (`.active-orchestrator-state.json`, §4.2 I/O matrix).
The `kb` section's shape has not changed since v2 — only OTHER top-level sections were
added additively (`registry` in v3, `discovery` in v4). That's why the write hook below
checks `version >= 2`, not an exact match: an exact `version == 2` check would silently
stop writing `state.kb` the moment the orchestrator bumped past v2, which is exactly what
happened in production once `registry` shipped (v3) — this file is the fix for that.

---

## 1. Schema slice

kb-creator is the **sole writer** of the `kb` object inside `.active-orchestrator-state.json`.
It NEVER touches `step`, `owner`, `roadmap`, `skills`, or `agents`.

```json
{
  "version": 4,
  "discovery": {
    "created_by": "discovery-research",
    "problema": "<same idea as kb.discovery.problem, but written by discovery-research, if that phase ran>",
    "...": "see discovery-research's own references/state-contract.md for the full shape — kb-creator only READS this, never writes it"
  },
  "kb": {
    "created_by": "kb-creator",
    "source": "ingest | interactive",
    "discovery": {
      "problem":      "<one-sentence description of the core problem being solved>",
      "system_type":  "<web_app | api | cli | mobile | saas_multi_tenant | ...>",
      "domain":       "<business domain, e.g. ecommerce, fintech, logistics>",
      "scale":        "<single_user | team | public_multi_user | multi_tenant>",
      "stack":        "<primary technologies, e.g. FastAPI + React + Postgres>",
      "needs_infra":  true
    },
    "files": [
      "knowledge-base/01_vision_y_objetivos.md",
      "knowledge-base/02_descripcion_general.md",
      "..."
    ]
  }
}
```

> The top-level `discovery` section (product/market discovery — problem, users,
> competitors, business rules; added in v4) is a **separate** concept from
> `kb.discovery` (architecture-oriented — system_type, scale, stack; exists since
> v2). They're not
> the same object. `kb-creator` only ever WRITES `kb.discovery`; it may READ the
> top-level `discovery` section (when present) to avoid re-asking what it already
> answers — see §5.

Fields:
| Field | Type | Description |
|---|---|---|
| `created_by` | string | Always `"kb-creator"` — identifies the writer. |
| `source` | enum | How the KB was built: `"ingest"` (Mode A) or `"interactive"` (Mode B). |
| `discovery` | object | Six-field project discovery (see §3). |
| `files` | string[] | Paths of every `knowledge-base/*.md` written (canonical + optional extras). |

---

## 2. Conditional write algorithm

Run this hook **after** `knowledge-base/` is fully written, before returning to the user.

```
1. Check project root for `.active-orchestrator-state.json`
   ├─ ABSENT  → no-op. Do NOT create the file. Done.
   ├─ PRESENT, version < 2 → surface one-line note:
   │    "State file predates the kb contract (version < 2), skipping state update."
   │    Continue. Done.
   └─ PRESENT, version >= 2 → update ONLY state.kb:
        • Before asking/inferring (see §4): check for a top-level `discovery`
          section (written by discovery-research, present only if that phase
          ran — see §5). If present, use it to pre-fill what you can instead
          of re-asking/re-inferring those fields from scratch.
        • Set created_by: "kb-creator"
        • Set source: (see §3 Mode→source mapping)
        • Set discovery: (see §4 inference / ask rules, informed by §5 if applicable)
        • Set files: list of all knowledge-base/*.md paths written
        Write the file back. Done.
```

**Why `version >= 2`, not `version == 2`**: `state.kb`'s own shape hasn't changed
since v2 — every version bump since (`registry` in v3, top-level `discovery` in
v4) added OTHER sections, additively, without touching `kb`. An exact-match check
would stop this hook from ever firing again the moment the orchestrator moved past
v2, silently — which is what happened in production between v2 and v3 before this
fix. If a future version bump ever DOES change `kb`'s shape, gate on that
specific version instead of tightening this back to an exact match.

**Why never create**: the orchestrator (active-orchestrator) is the sole creator of the state file (C-13a D3). kb-creator updating-only avoids two writers racing to create it.

**Why strictly conditional**: kb-creator is a public standalone skill. Forcing a state file on every direct invocation would regress standalone projects and pollute non-orchestrated repos.

---

## 3. Mode → `source` mapping

| Existing mode | `state.kb.source` | Rationale |
|---|---|---|
| **Mode A** (silent, from `docs/`) | `"ingest"` | KB built from existing user-supplied documents — maps to the contract's "ingest" definition. |
| **Mode B** (interactive, from scratch) | `"interactive"` | KB built via strategic Q&A discovery — maps to the contract's "interactive". |

**Dominant-origin rule (mixed runs)**: a run that started from `docs/` (Mode A trigger) resolves to `"ingest"` even if some gaps were later clarified by questions. The origin of the bulk of the content determines `source`. A pure from-scratch run is always `"interactive"`. The enum is frozen at `ingest | interactive`; no third value is introduced.

---

## 4. Discovery-field population

### Mode B (interactive) — ASKED

All six fields are obtained from the user's strategic Q&A answers. Map question → field:

| Discovery field | Sourced from |
|---|---|
| `problem` | P1 (Visión y problema raíz) |
| `system_type` | P0-sys (¿Qué tipo de sistema es?) — see `strategic-questions.md` §P0-sys |
| `domain` | P3 (Actores principales → business domain inferred) |
| `scale` | P0-scale (¿A qué escala opera?) — see `strategic-questions.md` §P0-scale |
| `stack` | P4 (Restricciones técnicas no negociables → stack) |
| `needs_infra` | P4 sub-questions (Cloud, on-prem, DB, queues → boolean) |

After collecting answers, record the values in `state.kb.discovery` before returning.

### Mode A (ingest) — INFERRED from source docs

Mode A is fire-and-forget (no questions). Inference rules per field:

| Field | Infer from | Signal to look for |
|---|---|---|
| `problem` | `01_vision_y_objetivos.md` (generated) | Vision / objective statement — the first declarative sentence about what the system solves. |
| `system_type` | `02_descripcion_general.md` (generated) | Architecture / overview section — keywords: "web app", "REST API", "CLI", "mobile", "SaaS", "multi-tenant". |
| `domain` | `03_actores_y_roles.md` + `06_funcionalidades.md` | Business domain implied by actor names + feature groupings (ecommerce → products/cart/checkout; fintech → transactions/ledger). |
| `scale` | `03_actores_y_roles.md` + any scale/RBAC mentions | "single user" / "team" / "public" / "multi-tenant" — infer from actor count, RBAC complexity, or scale keywords in the docs. |
| `stack` | `02_descripcion_general.md` | Technology names (frameworks, languages, database, external services). |
| `needs_infra` | `02_descripcion_general.md` + `08_arquitectura_propuesta.md` | Boolean: `true` if docs mention Docker, a database, Redis, message queues, cron jobs, or specific deployment infra. |

### Low-confidence rule (Mode A)

**Never invent** a confident discovery value. When a field cannot be inferred with reasonable confidence:

1. Set a best-effort value clearly marked as uncertain (e.g. `"web_app (inferred, low confidence)"`).
2. Add an entry to `10_preguntas_abiertas.md`:
   ```
   [DISCOVERY] `<field>` could not be inferred with confidence from the source docs.
   Please confirm: <what you need to know>.
   ```
3. Continue — never block Mode A on a single uncertain field.

---

## 5. Pre-fill from `discovery-research` (optional upstream input)

If `active-orchestrator` ran the optional Discovery phase before dispatching
`kb-creator`, the state file carries a top-level `discovery` section (owned by
`discovery-research`, NOT the same object as `kb.discovery` — see §1). Read it
if present, in BOTH modes, before asking (Mode B) or inferring (Mode A):

| From `discovery.<field>` | Pre-fills `kb.discovery.<field>` | How |
|---|---|---|
| `problema` | `problem` | Direct copy — it's the same question asked earlier by a different phase. |
| `usuarios` (size/nature of the audience) | `scale` | Orientative only — infer a starting value, but still confirm/ask if ambiguous. Never treat this as authoritative on its own. |
| `integraciones` (any that imply the project needs its own backend infra) | `needs_infra` | If any integration listed isn't purely client-side, set `true`; otherwise leave for the normal ask/infer path. |

`system_type` and `stack` are near-never derivable from product discovery (they're
technical decisions, not business ones) — keep asking/inferring them normally
unless the user explicitly mentioned a stack during Discovery.

**In Mode B**: when a field is pre-filled this way, don't ask the corresponding
question fresh — show what you already know and ask the user to confirm or
correct it instead (same "resumen a confirmar" pattern used to close every
round, see main `SKILL.md`). This is the entire point of running Discovery
first: it removes repeated questions, it doesn't just add more of them.

**In Mode A**: a pre-filled field from `discovery` takes priority over one
inferred from `docs/` when the two would conflict — `discovery` came from a
direct answer or real competitor research, `docs/` inference is a guess. If
they agree, no issue; if they disagree, note the discrepancy in
`10_preguntas_abiertas.md` instead of silently picking one.

**If the top-level `discovery` section is absent or `{"skipped": true}`**:
behave exactly as before this change — ask/infer every field from scratch, no
different than a project that never had this feature.
