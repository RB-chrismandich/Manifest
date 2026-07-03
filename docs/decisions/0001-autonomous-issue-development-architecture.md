# ADR 0001 — Autonomous issue development: evolve the skill, not a daemon

**Status**: Accepted · **Date**: 2026-06-15
**Deciders**: repo owner · **Context**: PR #346 (issue-orchestrator) vs merged PR #354 (issue-dev-auto)

## Context

Two implementations of the same goal — *autonomously take one opted-in issue →
implement → open a PR (never merge), one issue at a time* — were in flight:

- **issue-dev-auto (#354, merged):** a skill + `auto_issue_dev.sh` + `/loop`;
  runs in the Claude Code session; TDD via `superpowers`; `/project-verify`; allowlist
  `auto-dev` label.
- **issue-orchestrator (#346, open):** a polling Python **daemon** + stateless
  6-phase decision engine, consensus gates, `agy` dual-model, redacted audit
  log, denylist `no-automation` label — ~4031 LOC.

They overlap ~75% in responsibility. They also use **inverted opt-in models**
(allowlist `auto-dev` vs denylist `no-automation`), which cannot share a backlog
unambiguously.

## Decision

**Keep #354 as the foundation; harvest #346's three high-value ideas into it;
drop the daemon.** Do not merge #346 as a standalone system.

| Dimension (long-term) | issue-dev-auto (#354) | orchestrator daemon (#346) |
|---|---|---|
| Maintenance surface | ~1 script + skill | ~4031 LOC second runtime |
| Reuse vs reinvent harness | Reuses `/loop`, skills, `parallel_agent.py` | Re-implements looping/phases/consensus outside the session |
| Autonomous-output safety | Thin (`/project-verify` only) | Strong (consensus + Tier 1/2 gates) |
| Auditability | None | Redacted append-only log |
| Failure/reliability | In-session; no state to corrupt | Daemon lifecycle + persisted state |
| Status | Shipped, working | Unmerged, large review |

**Disqualifier for #346 as the base:** it stands up a second orchestration
runtime to do work the harness already does — the long-term tax is maintaining
two engines. **Disqualifier for #354 as the endpoint:** no verification gate and
no audit trail makes unattended autonomy unsafe at scale.

The value of #346 lives in three features, not its runtime; those are harvested:

- **#358** — unblock-aware prioritization in `next-issue` (`auto-dev`)
- **#359** — redacted append-only audit log (`auto-dev`)
- **#360** — post-implementation verification gate via existing `parallel_agent.py`
  (`planned`, human-led — reshapes the autonomy pipeline and has open design
  questions)

## Consequences

- **One label model:** `auto-dev` (allowlist, fail-closed) is the standard; the
  denylist `no-automation` introduced by #346 is retired when that PR closes.
- Tunables stay in config, not hard-coded: gate consensus threshold
  (`command_config.yml`), prioritization weights (unblock-vs-severity).
- `specs/004-autonomous-issue-orchestrator/` is preserved as the design source
  for #358–#360, then #346 is closed.
- We accept staying coupled to the Claude Code session / `/loop` model (no
  fully-decoupled external runtime) — that platform coupling is intentional.
