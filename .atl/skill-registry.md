# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

`_shared/skill-resolver.md` describes the full resolution protocol (not present in this workspace).

**Project**: Gestión Odontológica PyME (`odontologia-saas`, repo `-turnosodontologia`)
**Stack actual (2026-10-11)**: Python 3.12 (FastAPI) + React/Vite · PostgreSQL 16 (RLS) · Redis 7 (Celery) · Tailwind + shadcn/ui · pytest/Vitest · Playwright · OpenTelemetry/Sentry.

---

## Methodology Skills (project-local, `.agents/skills/`)

Vendored into the repo so the project is self-contained. The upstream copies still live under `~/.config/opencode/skills/`; these are the ones this project resolves.

| Trigger | Skill | Path |
|---------|-------|------|
| `/active-orchestrator:init\|kb\|rules\|discovery\|openspec\|devops\|find-skill\|registry` — or starting a new project from scratch via the SDD/OpenSpec foundation flow | active-orchestrator | .agents/skills/active-orchestrator/SKILL.md |
| Create/generate/update `AGENTS.md`/`CLAUDE.md`, "armar las reglas del proyecto", "instrucciones para los agentes", "generar claude.md"; or after kb-creator + roadmap-generator | agents-md-generator (agent-instruction) | .agents/skills/agent-instruction/SKILL.md |
| Research the market / think what to build before clarity; dispatched as the pre-KB discovery phase | discovery-research | .agents/skills/discovery-research/SKILL.md |
| "how do I do X", "find a skill for X", "is there a skill that can...", or extending agent capabilities | find-skills | .agents/skills/find-skill/SKILL.md |
| Create/build/generate a knowledge base, document a project from source docs, "armar base de conocimiento", "crear KB", "documentar proyecto" | kb-creator | .agents/skills/kb-creator/SKILL.md |
| Create/build/regenerate/update `CHANGES.md`, roadmap, change map, implementation plan; "armar CHANGES", "crear mapa de changes" | roadmap-generator | .agents/skills/roadmap-generator/SKILL.md |
| Create/modify/improve a skill, run evals, benchmark, or optimize a skill description for triggering | skill-creator | .agents/skills/skill-creator/SKILL.md |
| Build or update the project skill registry (`.atl/skill-registry.md`) | skill-registry | .agents/skills/skill-registry/SKILL.md |
| Research/scrape a competitor from a URL, or `discovery-research` invokes it during Discovery | web-scraper | .agents/skills/web-scraper/SKILL.md |

### Domain Skills (project-local, `.agents/skills/`)

Vendored from `~/.agents/skills/` into the repo.

| Trigger | Skill | Path |
|---------|-------|------|
| Writing, reviewing, or refactoring NestJS code (legacy — stack anterior; el backend actual es FastAPI/Python) | nestjs-best-practices | .agents/skills/nestjs-best-practices/SKILL.md |
| Automate browser interactions, test web pages, work with Playwright tests | playwright-cli | .agents/skills/playwright-cli/SKILL.md |
| Writing DB queries, CRUD, filtering, or configuring Prisma Client (legacy — stack anterior; el ORM actual es SQLAlchemy 2.0 + Alembic) | prisma-client-api | .agents/skills/prisma-client-api/SKILL.md |
| Working with shadcn/ui, component registries, presets, `components.json`; "shadcn init"; design system from DESIGN.md | shadcn | .agents/skills/shadcn/SKILL.md |
| BEFORE writing/changing anything in a Postgres DB — schema, migration, RLS, index, query; diagnosing slow queries/locks/RLS leaks | supabase-postgres-best-practices | .agents/skills/supabase-postgres-best-practices/SKILL.md |
| Build features or fix bugs test-first, "red-green-refactor", or want integration tests | tdd | .agents/skills/tdd/SKILL.md |
| Writing/reviewing/refactoring React code (vigente; aplica a React 18 + Vite); performance, data fetching, bundle optimization | vercel-react-best-practices | .agents/skills/vercel-react-best-practices/SKILL.md |

### Project Skills (OPSX/OpenSpec — deduplicated)

Identical copies exist under `.opencode/skills/` and `.claude/skills/`. Deduplicated to the `.opencode/skills/` copies (active OpenCode harness); the `.claude/skills/` copies are equivalent.

| Trigger | Skill | Path |
|---------|-------|------|
| Start/continue implementing tasks from an OpenSpec change; "openspec apply", "opsx apply", "openspec implement" | openspec-apply-change | .opencode/skills/openspec-apply-change/SKILL.md |
| Finalize and archive a completed change; "openspec archive", "opsx archive" | openspec-archive-change | .opencode/skills/openspec-archive-change/SKILL.md |
| Think through something before/during a change; "openspec explore", "opsx explore" | openspec-explore | .opencode/skills/openspec-explore/SKILL.md |
| Quickly describe what to build and get a complete proposal (design, specs, tasks); "openspec propose", "opsx propose" | openspec-propose | .opencode/skills/openspec-propose/SKILL.md |
| Update main specs from a delta spec without archiving; "openspec sync", "opsx sync" | openspec-sync-specs | .opencode/skills/openspec-sync-specs/SKILL.md |
| Revise a change's existing planning artifacts and keep them coherent; "openspec update change", "opsx update" | openspec-update-change | .opencode/skills/openspec-update-change/SKILL.md |

---

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### project-conventions (odontologia-saas)
- **Strict TDD is ON for this project.** Red before green: failing test first, then minimal code to pass. One vertical slice (test → implementation → repeat) at a time.
- **Agent model**: `sdd-orchestrator` is the primary/coordinator agent — it NEVER executes work inline, it delegates to executor sub-agents via the `task` tool and synthesizes results. `openspec` CLI is the single source of truth for artifact state.
- **Governance by domain criticality** (BAJO / MEDIO / ALTO / CRITICO). 8 CRITICO changes: C-02, C-03, C-09, C-10, C-13, C-15, C-16, C-17. CRITICO = auth, ARCA billing, clinical history, audit trail, core tenancy models. Extra review + tests required.
- **RN-TEN-02 is a merge gate, not a suggestion**: any change touching a table with `tenant_id` is NOT done until it has a cross-tenant isolation test. `cross-tenant leak = 0`. RLS active on every business table (`tenant_id NOT NULL`).
- Build in **vertical slices** (DD-03): each change delivers API + UI of its capability (not layer-by-layer).
- Start order: C-01 → C-02 → C-03 are strictly sequential and block all else; first real fork is GATE 3. Read `CHANGES.md` before any `/opsx:propose`.

### active-orchestrator
- Thin orchestrator: only routes to sub-skills; NEVER reimplements a phase's logic.
- Owns `.active-orchestrator-state.json` and ONLY the `step` field; sub-skills write their own sections.
- Flow order: `openspec init` → [discovery-research?] → kb-creator → roadmap-generator → find-skill → skill-registry → agent-instruction.
- Interactive phases run inline (`Skill`); mechanical phases run as sub-agents (`Agent`). Interactivity decides placement.
- NEVER advance `step` without an explicit user "Continuar"; hold a checkpoint at every phase boundary.
- NEVER install skills autonomously — `find-skill` recommends only; the orchestrator owns the install decision after the user picks.
- Resume by default if state exists and `step != "done"`; never chain phases silently.

### agents-md-generator (agent-instruction)
- Output `AGENTS.md` + `CLAUDE.md` at the project ROOT with the SAME content (copies, not references); never inside `.claude/` or `openspec/`.
- Pre-checks: `knowledge-base/` must exist; `CHANGES.md` optional (omit roadmap section if absent, warn).
- Read: KB `02` (stack), KB `README`, `CHANGES.md`, `.atl/skill-registry.md` (skills source of truth), KB `10`, and global `~/.claude/CLAUDE.md`.
- Do NOT repeat global rules — only project-specific rules + universals the global misses (verify, don't assume).
- Hard rules are stack-aware (derived from the REAL stack), confirmed by the user — never hardcode a language.
- Map a skill→agent-role table; REFERENCE the registry for compact rules — never copy them in (DRY).
- Only interactive step is confirming hard rules via `AskUserQuestion`, then STOP and wait.

### discovery-research
- Runs BEFORE kb-creator; product/market discovery (problem, users, competitors, business rules, risks).
- Invokes `web-scraper` per URL if the user provides any; also works with pure Q&A (no URLs required).
- Guided Q&A over the 11-point checklist (3-5 questions/round, options a/b/c, "why it matters").
- Never re-ask what scraping already answered — show it as a summary to confirm/correct.
- Final gate: show the 11-point summary and wait for explicit confirmation before writing anything.
- Output ONLY `discovery/discovery.md` + the top-level `state.discovery`.

### find-skills
- Check the skills.sh leaderboard first, then `npx skills find [query]`.
- Verify before recommending: install count (prefer 1K+), source reputation, GitHub stars.
- Install: `npx skills add <owner/repo@skill> -g -y` (`-g` global, `-y` skips prompts).
- In recommend-only mode: DO NOT install, DO NOT run `npx skills add` — return the table and let the delegator/user pick.

### kb-creator
- Output the 10 canonical files to `knowledge-base/` at the project ROOT; NEVER mix with `docs/`.
- Canonical names: `01_vision_y_objetivos`, `02_descripcion_general`, `03_actores_y_roles`, `04_modelo_de_datos`, `05_reglas_de_negocio`, `06_funcionalidades`, `07_flujos_principales`, `08_arquitectura_propuesta`, `09_decisiones_y_supuestos`, `10_preguntas_abiertas` + `README.md`.
- Mode A (`docs/` has sources): silent/ingest, no questions; record doubts in file 10.
- Mode B (from scratch): interactive strategic Q&A (3-5 questions), validate per file.
- Never invent values; unknown → `10_preguntas_abiertas.md`.
- Optional extras use `1X_`/`2X_` prefix and never replace the 10 canonicals.
- If orchestrated: write ONLY `state.kb` (never touch `step`/`owner`/other sections).

### roadmap-generator
- Pre-checks: `knowledge-base/` with the 10 canonicals AND `openspec/` exists; otherwise generate nothing.
- Output a single `CHANGES.md` at the project ROOT (never inside `openspec/`).
- IDs: sequential `C-NN` (2-digit padding), kebab-case, NO `us-NNN-` prefix.
- Dependency order: infra → core-models → auth → referenced entity before referrer → backend before coupled frontend → integrations/payments/webhooks last.
- Every change MUST have: Estado, Scope (operational bullets), Dependencias, Governance (BAJO/MEDIO/ALTO/CRITICO), Leer antes.
- Include dependency tree, GATES, critical path and 3-agent plan — never drop top-level sections (they are contract).
- If orchestrated: write ONLY `state.roadmap`.

### skill-creator
- Core loop: draft skill → run test prompts (with-skill + baseline in parallel) → user reviews via `eval-viewer/generate_review.py` → improve → repeat.
- `description` is the primary trigger; make it "pushy", include WHAT it does AND WHEN to use it.
- Keep `SKILL.md` under ~500 lines; use progressive disclosure (metadata → body → bundled `scripts/`/`references/`/`assets/`).
- Save evals to `evals/evals.json`; outputs to `<skill>-workspace/iteration-N/eval-ID/`.
- Always generate the eval viewer for human review BEFORE self-evaluating.
- Offer description optimization (`run_loop.py`) only after the skill is in good shape.

### web-scraper
- Input: one or more http(s) URLs of competitors; add the scheme if missing.
- `WebFetch` with a prompt for the 8 FIXED fields → write `discovery/sources/<slug>.md`.
- The output schema is non-negotiable; unpublished field → `(no publicado)`; NEVER invent data.
- File name via `slugify` (kebab-case) so re-runs overwrite instead of duplicating.
- On empty/SPA-shell/403/paywall: report the limitation, no evasion tricks, continue with the next URL.
- No full-site crawling; one page per explicit URL.

### nestjs-best-practices
- 40 rules / 10 categories. Priorities: Architecture + DI CRITICAL; Error/Security/Perf HIGH; Testing/DB MEDIUM-HIGH; API/Microservices MEDIUM; DevOps LOW-MEDIUM.
- Organize by FEATURE module (not technical layer); use constructor injection; injection tokens for interfaces; avoid service-locator and circular deps.
- Centralized exception filters; throw Nest HTTP exceptions; validate ALL input with `class-validator`; auth/authorization guards; rate limiting.
- Perf/DB: transactions, avoid N+1, migrations for schema changes, caching, lazy-load modules, DTO serialization, interceptors, API versioning, health checks.
- Prefixes: `arch-`, `di-`, `error-`, `security-`, `perf-`, `test-`, `db-`, `api-`, `micro-`, `devops-`.

### playwright-cli
- Drive with `playwright-cli`; if global is unavailable use `npx playwright cli` (or install `@playwright/cli`).
- Snapshot to get element refs; interact via refs (`click e15`) or CSS/locator/`getByTestId`.
- Prefer `snapshot` over screenshots; use `find`/`--depth` to search large snapshots efficiently.
- Use `route`/`unroute` for request mocking; `console`/`requests`/tracing/video for debugging.
- Windows: escape `&` (`^&` in cmd, `--%` in PowerShell) or URLs with query params get truncated.
- `--raw` strips metadata for piping; `--json` for structured output.

### prisma-client-api
- Instantiate via adapter: `new PrismaClient({ adapter: new PrismaPg({ connectionString }) })`; import from the generated client.
- Methods: `findUnique/findFirst/findMany/create/createMany/update/updateMany/upsert/delete/count/aggregate/groupBy`.
- Query options: `where`, `select`, `include`, `omit`, `orderBy`, `take`, `skip`, `cursor`, `distinct`.
- Filters: `equals`, `not`, `in`, `notIn`, `lt/lte/gt/gte`, `contains/startsWith/endsWith`, `mode`.
- Relation filters: `some`/`every`/`none`/`is`/`isNot`.
- Use `$transaction` for atomicity; `$queryRaw`/`$executeRaw` for raw SQL; `$extends`/`$on` for extensions/events.

### shadcn
- Check `components.json` / `npx shadcn@latest info` first; use existing components before custom markup.
- Compose, don't reinvent; use built-in variants and SEMANTIC colors (`bg-primary`, `text-muted-foreground`) — never raw `bg-blue-500`.
- `className` for layout only; `gap-*` not `space-x/y-*`; `size-*` for equal dims; no manual `dark:` overrides; `cn()` for conditional classes.
- Forms: `FieldGroup` + `Field`; validation via `data-invalid` (Field) + `aria-invalid` (control); `InputGroup` for input+button.
- Always run `npx shadcn@latest docs <component>` and fetch the URLs before using a component.
- NEVER `--overwrite` without explicit approval; use `--dry-run`/`--diff` to merge updates.
- Never guess a registry — ask which registry when unspecified.

### supabase-postgres-best-practices
- Load BEFORE ANY Postgres change (schema, column type, migration, RLS, index, trigger, function, query).
- Priorities: query performance + connection management + security/RLS CRITICAL; schema design HIGH; locking MEDIUM-HIGH; data access MEDIUM; monitoring LOW-MEDIUM; advanced LOW.
- Category prefixes: `query-`, `conn-`, `security-`, `schema-`, `lock-`, `data-`, `monitor-`, `advanced-`.
- RLS is required for tenant isolation — verify policies and their tests; diagnose slow queries, EXPLAIN, locks, connection exhaustion.
- Applies to schema/security/SQL authoring, not just performance — even a one-column change.

### tdd
- Red → green loop: write the failing test first, then only enough code to pass.
- Test behavior through PUBLIC interfaces (seams), never internals; a good test reads like a spec.
- Agree on the seams under test with the user BEFORE writing any test.
- Anti-patterns: implementation-coupled, tautological (expected value recomputed like the code), horizontal slicing.
- Work in VERTICAL slices — tracer bullets: one test → one implementation → repeat.
- Refactoring is NOT part of the loop (belongs to review).

### vercel-react-best-practices
- 70 rules / 8 categories. CRITICAL: eliminate waterfalls (`async-`) + bundle size (`bundle-`).
- HIGH: server-side perf (`server-`); MEDIUM-HIGH: client data fetching (`client-`); MEDIUM: re-render (`rerender-`) + rendering (`rendering-`); LOW-MEDIUM: JS perf (`js-`); LOW: advanced.
- Use `Promise.all()` for independent ops; defer `await` into the branches that use it; import directly (avoid barrel files); `next/dynamic` for heavy components.
- `React.cache()` for per-request dedup; authenticate server actions; avoid module-level mutable request state; minimize RSC→client serialization.

### openspec-apply-change
- Requires `openspec` CLI + a project root (`openspec list --json` → root object). NEVER run `openspec init` as a side effect.
- If a store is selected, keep `--store <id>` sticky on every spec/change command.
- `openspec status --change "<n>" --json` then `openspec instructions apply --change "<n>" --json`; read every `contextFiles` path.
- Implement tasks minimally; mark `- [ ]`→`- [x]` at the returned `sourcePath`/`line`; rerun instructions to confirm progress.
- Pause on blocked/unclear/new scope; NEVER silently narrow, defer, or simplify specified behavior.
- This skill only implements; when `all_done`, suggest archive.

### openspec-archive-change
- Verify root; check artifact completion (`openspec status --json`) and task counts (`openspec list --json`).
- Warn (don't block) on incomplete artifacts/tasks; ask the user to confirm.
- Assess delta specs vs main specs at `<root>/openspec/specs/<capability-path>/spec.md`; prompt sync options.
- Run `openspec-sync-specs` INLINE (synchronously, never background) BEFORE moving `changeRoot`; verify main specs.
- Move `changeRoot` → `changes/archive/YYYY-MM-DD-<name>`; never stack a second date.
- Never archive while a spec sync is in flight; never copy delta headers into main specs.

### openspec-explore
- Thinking mode ONLY — never write code or implement. Capturing artifacts within confirmed scope is OK.
- Offer to capture insights; do NOT auto-capture. Before the first write, name files + ask a direct yes/no and wait.
- NEVER hand-create change dirs — use `openspec new change "<name>"` (creates `.openspec.yaml`).
- Ground in `openspec list --json`, `openspec list --specs`, and `<root>/openspec/config.yaml` (`context` + `rules`).
- Visualize with plain ASCII only; ground discussions in the real codebase.
- Handoff to `/opsx-propose` to plan; explore doesn't implement.

### openspec-propose
- Planning ONLY — never edit project code or start apply in the same response.
- `openspec new change "<name>"`, then create EVERY artifact in the transitive required set (walk `requires` edges, not just `applyRequires`).
- Use `openspec instructions <artifact> --change "<n>" --json`; treat `context`/`rules` as constraints and NEVER copy them into the file.
- Re-read dependency files from disk; verify each artifact exists after writing.
- `specs/<capability-path>/spec.md` is a DELTA (ADDED/MODIFIED/REMOVED/RENAMED), not a main spec.
- Stop after artifacts; the user starts apply separately.

### openspec-sync-specs
- Agent-driven merge of delta specs into main specs at `<root>/openspec/specs/<capability-path>/spec.md`.
- Only source of deltas: `artifactPaths.specs.existingOutputPaths` (honor a caller-supplied subset; never widen it).
- New capability: ONLY ADDED creates the main spec; MODIFIED/RENAMED block; REMOVED skipped (retire only if `retire_capabilities: true`).
- Merge intelligently: preserve content not mentioned; MODIFIED carries the full requirement + surviving scenarios.
- NEVER leave an empty `## Requirements`; NEVER copy delta headers into the main spec.
- Run `openspec validate --specs`; fetch specs instructions once (or reuse the archive snapshot).

### openspec-update-change
- Revises EXISTING planning artifacts only; never creates missing ones; NEVER edits code.
- Edit only concrete files in `artifactPaths.<id>.existingOutputPaths`; never write a glob `resolvedOutputPath`.
- Build order is a reading order, not a constraint — edits may flow in any direction.
- Draft edits in the conversation; show each revision and write only after the user confirms, one artifact at a time.
- Leave `skipped` artifacts untouched; point ready/blocked artifacts to `openspec instructions`.
- If the request changes intent → suggest a distinct new change via `openspec new change`.

---

## Project Conventions

The canonical convention index files now exist: `AGENTS.md` / `CLAUDE.md` at the project ROOT (identical copies, generated by `agent-instruction`/`agents-md-generator`). Convention-bearing files discovered:

| File | Path | Notes |
|------|------|-------|
| Roadmap / change index | `CHANGES.md` | Canonical index of 23 changes (C-01…C-23), dependency tree, GATES, critical path, governance per change. Read before any `/opsx:propose`. Encodes RN-TEN-02 merge gate + vertical-slices rule. |
| KB index | `knowledge-base\README.md` | Index of the 13 KB files; executive summary; the two highest-risk pieces (ARCA billing, legal clinical history). |
| Vision & scope | `knowledge-base\01_vision_y_objetivos.md` | Purpose, compliance-first positioning, actors, MVP scope (v0.1). |
| Stack & architecture | `knowledge-base\02_descripcion_general.md` | Stack TypeScript, multi-tenant architecture, integrations, REST surface. |
| Actors & RBAC | `knowledge-base\03_actores_y_roles.md` | 9 actors, RBAC matrix, public routes. |
| Data model | `knowledge-base\04_modelo_de_datos.md` | 8 domains, ERD, ~30 entities, tenant isolation, seed data (RN-TEN-02). |
| Business rules | `knowledge-base\05_reglas_de_negocio.md` | Coded RN rules in 9 domains (RN-TEN-02: every business table has `tenant_id NOT NULL` + RLS). |
| Features | `knowledge-base\06_funcionalidades.md` | 10 epics, 38 user stories with acceptance criteria. |
| Main flows | `knowledge-base\07_flujos_principales.md` | 6 end-to-end flows with error cases. |
| Architecture proposal | `knowledge-base\08_arquitectura_propuesta.md` | Patterns, directory structure, security, env vars; cross-tenant tests gate. |
| Decisions & assumptions | `knowledge-base\09_decisiones_y_supuestos.md` | 11 decisions (DD) + 9 assumptions (SU). |
| Open questions | `knowledge-base\10_preguntas_abiertas.md` | 5 inconsistencies + 11 prioritized questions; cross-tenant checklist. |
| ARCA billing (extra) | `knowledge-base\11_facturacion_arca.md` | A/B/C/M invoices, WSAA, X.509 per tenant, idempotency; RN-TEN-02 checklist. |
| Clinical history & compliance (extra) | `knowledge-base\12_historia_clinical_y_compliance.md` | Ley 26.529, Ley 25.326 + AAIP, immutability, authenticated copy. |
| Competitive research | `discovery\discovery.md` | 20-competitor market research (2026-10-01); `[C]`/`[A]`/`[NE]` evidence markers. |
| OpenSpec config | `openspec\config.yaml` | `schema: spec-driven`; context/rules sections still empty. |
| Foundation state | `.active-orchestrator-state.json` | Version 4; `step: implementation` (foundation complete; Sprint 1 dev en curso). |
| OpenCode agent config | `C:\Users\L\.config\opencode\opencode.json` | Primary agent `sdd-orchestrator` (coordinator, delegates via `task` tool). |
| Agent instructions | `AGENTS.md` / `CLAUDE.md` | Canonical instruction files at project root (stack, KB, skills-per-agent, roadmap, hard rules). |

Now that `AGENTS.md`/`CLAUDE.md` exist, they are the canonical convention index; regenerate this registry when skills change.

> **Nota de stack (2026-10-11)**: Stack actualizado a Python/FastAPI + React/Vite el 2026-10-11; regenerar este registry con la skill `skill-registry` para agregar skills de Python cuando se instalen.
