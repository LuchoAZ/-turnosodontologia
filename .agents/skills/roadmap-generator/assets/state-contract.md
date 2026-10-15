# State Contract — roadmap-generator owns `state.roadmap`

Reference: C-13a frozen contract (`.active-orchestrator-state.json` v2, §4.2 I/O matrix).

---

## 1. Schema slice

roadmap-generator is the **sole writer** of the `roadmap` object inside `.active-orchestrator-state.json`.
It NEVER touches `step`, `owner`, `kb`, `skills`, or `agents`.

```json
{
  "version": 2,
  "roadmap": {
    "created_by": "roadmap-generator",
    "source": "CHANGES.md",
    "changes": ["C-01", "C-02", "C-03"]
  }
}
```

Fields:

| Field | Type | Description |
|---|---|---|
| `created_by` | string | Always `"roadmap-generator"` — identifies the writer (mirrors `state.kb.created_by`). |
| `source` | string | Path of the generated index — always `"CHANGES.md"` (mirrors how `state.kb.files` records produced paths). |
| `changes` | string[] | The `C-NN` change IDs generated, in order — lets downstream phases and the orchestrator know the roadmap content without re-parsing `CHANGES.md`. |

**Thin index rationale**: per-change scope, governance, and dependencies stay ONLY in `CHANGES.md` (single source of truth). The slice is a thin index only — no duplication, no drift.

---

## 2. Conditional write algorithm

Run this hook **after** `CHANGES.md` is fully written, before returning to the user.

```
1. Check project root for `.active-orchestrator-state.json`
   ├─ ABSENT  → no-op. Do NOT create the file. Done.
   ├─ PRESENT, version != 2 → surface one-line note:
   │    "State file is not v2, skipping state update."
   │    Continue. Done.
   └─ PRESENT, version == 2 → update ONLY state.roadmap:
        • Set created_by: "roadmap-generator"
        • Set source: "CHANGES.md"
        • Set changes: list of C-NN IDs generated (in order)
        Write the file back. Done.
```

**Why never create**: the orchestrator (active-orchestrator) is the sole creator of the state file (C-13a D3). roadmap-generator updating-only avoids two writers racing to create it.

**Why strictly conditional**: roadmap-generator is a public standalone skill. Forcing a state file on every direct invocation would regress standalone projects and pollute non-orchestrated repos.

**Why never touch `step`**: the orchestrator owns `step` advancement. roadmap-generator signals completion only by writing `state.roadmap`; the orchestrator reads it to decide when to advance `step` to `"find-skill"`.

---

## 3. Orchestrated input rules

When running orchestrated (`.active-orchestrator-state.json` present and `version == 2`):

### 3.1 Reading KB files

- **Primary**: use `state.kb.files` as the authoritative list of `knowledge-base/*.md` paths to read, instead of globbing the directory. This is robust when the KB lives at a non-default path or has extras.
- **Fallback**: if `state.kb.files` is empty or absent, fall back to globbing `knowledge-base/` on disk (the standalone read path) so the phase still produces `CHANGES.md`.

### 3.2 Using `state.kb.discovery`

- Read `state.kb.discovery` as **context** for naming/grouping changes and inferring governance:
  - `needs_infra: true` → expect a foundation-setup change (typically C-01)
  - `system_type` → seed the FASE names (e.g. `web_app` → FASE 1: Infraestructura + Auth)
  - `domain` → infer domain-specific changes (e.g. ecommerce → categories/products/cart/checkout)
  - `scale` → infer whether RBAC or multi-tenancy changes are needed
- **Discovery is a hint only**: the KB files (`state.kb.files`) remain the source of truth for change scope. A wrong discovery field degrades naming quality but does NOT corrupt scope correctness.

### 3.3 Pre-checks when orchestrated

When `state.kb.files` is populated and used as the file list:
- Skip the `knowledge-base/` directory existence pre-check (files are resolved from state).
- Still verify that the listed files exist on disk before reading them.
- Still verify that `openspec/` exists at the project root.

When falling back to disk glob (no state or empty `state.kb.files`):
- Run all three standard pre-checks unchanged (see SKILL.md §Critical Patterns).

### 3.4 Standalone invariant

With no `.active-orchestrator-state.json`:
- The three pre-checks, the KB reads, the frozen `CHANGES.md` format, and the closing user output are **byte-for-byte identical to today**.
- The "Si orquestado" hook (§2) and the `state.kb` read (§3.1–3.2) never fire.
- No state file is created.
