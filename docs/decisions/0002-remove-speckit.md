# ADR 0002: Remove Spec Kit tooling (`.specify/`, `/speckit-*` commands)

**Status**: Accepted
**Date**: 2026-09-26

## Context

The repo adopted GitHub Spec Kit early on: a `.specify/` scaffold (templates,
bash/powershell prerequisite scripts, `extensions.yml` hooks), vendored
`/speckit-*` slash commands under `.claude/skills/`, and a generated
`specs/<NNN-slug>/` artifact convention. Over time the workflows spec-kit
automated were re-expressed natively: the nine-phase state-gated lifecycle moved
into the constitution (Principle VI) with `lifecycle.sh` + `/lifecycle-run` as
the enforced implementation, and the spec-* skills (`spec-review`,
`spec-audit-tasks`, `spec-decide-tradeoffs`, `spec-implement-loop`) now resolve
artifacts directly from the directory layouts rather than through spec-kit's
`check-prerequisites.sh`.

The scaffold had become dead weight: every lint/format/scan config carried
`.specify/` exclusions, the constitution ratchet baseline keyed violations
against scripts nothing invoked, and discovery docs told skills to prefer a
resolver that only existed for the removed workflow.

## Decision

Stage 1 (this change):

- Delete `.specify/` and `.claude/skills/speckit-*` entirely.
- Move the constitution to `docs/constitution.md` (a plain doc; the spec-kit
  constitution template machinery is gone).
- Keep `specs/` — it is permanent feature history and the "speckit" artifact
  layout (`spec.md`/`plan.md`/`tasks.md`) remains the contract the spec-* skills
  discover. `specs/` removal or re-homing is a separate stage-2 decision.
- Strip `.specify/`-era exclusions, baseline keys, and prose that pointed at
  the deleted scripts/commands. The `/speckit-*` command names are gone; the
  lifecycle SKILL phase map now names the native skill (or "agent pass") that
  executes each phase.

## Consequences

- No code path may rely on `.specify/` existing; artifact discovery is plain
  `specs/<n>/` globbing per `configs/claude/references/spec-artifact-discovery.md`.
- `constitution_baseline.json` no longer carries entries for deleted files.
- Historical records (`specs/`, `docs/superpowers/`, `CHANGELOG.md`,
  `docs/baselines/`) intentionally retain their spec-kit mentions — they are
  dated history, not live guidance.
