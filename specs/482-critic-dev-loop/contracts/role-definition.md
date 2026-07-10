# Contract: Role Definition Files

**Feature**: `482-critic-dev-loop` | Enforces spec FR-013, FR-014

Location (source of truth): `configs/claude/prompts/cddl/`
Deployed (read at runtime): `~/.claude/prompts/cddl/` via the standard bootstrap
rsync — zero bootstrap changes, no service toggle, no ownership marker (research D3).
The loop reads the deployed copies; `--state-root`-style override is not provided for
roles (Configuration-as-Code: edit the repo, redeploy).

## Files (fixed set, v1)

| File | role_key | Default model |
|---|---|---|
| `implementer.md` | `implementer` | `sonnet` |
| `qa-critic.md` | `qa_critic` | `sonnet` |
| `arch-critic.md` | `arch_critic` | `sonnet` |

Names deliberately share no filename with the six pilotfish role agents
(`scout.md`, `Explore.md`, `mech-executor.md`, `executor.md`, `verifier.md`,
`security-executor.md`) and live in a different namespace entirely — `prompts/`, not
the `~/.claude/agents/` subagent registry (placing them in `agents/` would
auto-register them as Claude Code subagents; FR-014).

## Format

```markdown
---
name: qa-critic                # MUST equal file stem
description: One-line purpose  # non-empty
model: sonnet                  # alias only (haiku|sonnet|opus) — never a dated model ID
---
(markdown body = the role's system prompt; non-empty)
```

Frontmatter is the repo's agent-definition convention; parsed with the
`---`-delimited split + `yaml.safe_load`. The draft's `settings.temperature` /
`settings.max_tokens` keys are NOT part of this contract (the CLI seam does not
expose them; research D4). Unknown extra keys are ignored with a warning (forward
compatibility) — except `provider`, which is reserved and rejected in v1
(clarification: Claude-only).

## Validation (pre-flight, FR-013)

Run refuses (exit 6, actionable message naming the file) when any role file is:
missing · unreadable · frontmatter unparseable · `name` ≠ file stem ·
`name`/`description`/`model` missing or empty · body empty.

## Prompt assembly (FR-012, D4)

Per invocation, stdin payload = role `prompt_body` + phase task instruction +
FeatureContext (spec, plan-or-absence-disclosure, clarifications) + (phase 2)
candidate/deficiency history + the verdict-format instruction
([verdict-format.md](verdict-format.md)). argv carries only
`-p --model <alias>`. Operators tune behavior by editing prompt body or model alias —
no code change (FR-013).
