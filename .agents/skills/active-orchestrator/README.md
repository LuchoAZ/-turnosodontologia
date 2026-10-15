# active-orchestrator

Thin orchestrator skill for the SDD/OpenSpec project foundation flow.

## What it does

`active-orchestrator` is a **thin** orchestrator. It does not generate any artifact itself — it dispatches each foundation phase to its dedicated sub-skill in order:

1. `openspec init` — scaffold the OpenSpec workspace
2. *(optional)* `discovery-research` — investigate the problem, users and competitors **before** documenting — only runs if you say yes to the Discovery gate right after `openspec init`
3. `kb-creator` — build `knowledge-base/` (discovery + canonical docs)
4. `roadmap-generator` — build `CHANGES.md` from the KB
5. `find-skill` — recommend agent skills for the detected stack
6. `agent-instruction` — generate `CLAUDE.md` / `AGENTS.md`

**Checkpoints between phases.** The full flow never runs phases back-to-back: it stops at every phase boundary so you can review what was produced and choose **continue / adjust / stop**. Where a phase depends on your judgment (the roadmap), it first asks if there's anything to take into account. And `find-skill` only *recommends* — nothing is installed into your global skills until you pick it at the install gate.

State is shared across phases via `.active-orchestrator-state.json` (schema v4, frozen contract).

## Triggers

| Command | Effect |
|---|---|
| `/active-orchestrator:init` | Full foundation flow |
| `/active-orchestrator:discovery` | Only `discovery-research` phase (standalone, skips the gate) |
| `/active-orchestrator:kb` | Only `kb-creator` phase |
| `/active-orchestrator:rules` | Only `agent-instruction` phase |
| `/active-orchestrator:openspec` | Only `openspec init` |
| `/active-orchestrator:find-skill` | Only `find-skill` phase |
| `/active-orchestrator:devops` | Optional devops scaffolding (full mode) |

## Install

```bash
npx skills add https://github.com/Group-Active-IA/active-orchestrator
```

## Architecture

This skill is part of the **Active Stack** foundation. The sub-skills (`discovery-research`, `kb-creator`, `roadmap-generator`, `find-skill`, `agent-instruction`) are independent skills, each in its own repo. `active-orchestrator` does **NOT** embed them — it dispatches via the `Skill` tool and falls back gracefully if a sub-skill is missing.

For the full architecture and frozen state contract, see [SKILL.md](SKILL.md).

## License

MIT
