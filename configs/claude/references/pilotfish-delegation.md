<!--
  Pilotfish-style cost-tiered delegation policy.
  Adapted from pilotfish (https://github.com/Nanako0129/pilotfish), MIT License,
  vendored from v1.1.0 (2026-07-08). Manifest owns this copy; upstream drift is
  reviewed periodically against the recorded version above.

  Upstream attribution (MIT — FR-011):
    Copyright (c) 2026 Nanako0129
    Permission is hereby granted, free of charge, per the MIT License; the full
    license text is at https://github.com/Nanako0129/pilotfish/blob/main/LICENSE.

  Deployed to ~/.claude/references/ and referenced (not inlined) from
  configs/claude/CLAUDE.md so it carries no always-loaded context cost.
-->

# Pilotfish Delegation Policy (cost-tiered model orchestration)

Read this before delegating cost-tiered work. It routes each unit of work to the cheapest
capable role, keeps the frontier model for planning/decision/review, and gates risky results
behind an independent verifier. Opt-in (`bootstrap.sh --enable-pilotfish`); deployed to both
the Claude home (`~/.claude/agents/`) and, since 2026-07-11 (cursor-feature-parity WS-5), the
Cursor home (`~/.cursor/agents/`, Cursor-native frontmatter — see
`configs/claude/scripts/generate_cursor_agents.py`). Gemini/Codex/Antigravity remain out of
scope (no subagent-file mechanism to deploy to).

## Model aliases

Roles name Claude Code's **built-in** model aliases directly — never a raw model ID and never a
custom name. Built-in aliases float to the current version, so no alias-definition file and no
`settings.json` change is deployed:

| Alias | Resolves to (current) | Cost intent |
|-------|-----------------------|-------------|
| `opus` | Opus 4.8 | high |
| `sonnet` | Sonnet 5 | mid |
| `haiku` | Haiku 4.5 | cheap |

The **orchestrator / frontier** model is the unchanged main session (whatever you already run) —
it is not a deployed alias. Model availability and fallback for built-in aliases are handled by
Claude Code; Manifest deploys no custom fallback chain.

**Pinned-version override fallback (FR-007)**: a role normally names a built-in alias. If a role
is ever pinned to a *specific* model ID (the documented FR-002 exception, when an exact version is
required), that role file MUST also record its fallback to the corresponding built-in alias —
e.g. a role pinned to `claude-opus-4-8` falls back to `opus` — so that when the pinned version is
retired the role degrades to the current tier instead of failing to resolve. Prefer the built-in
alias unless a specific version is genuinely required.

## Roles

| Role | Alias | Effort | Delegate for |
|------|-------|--------|--------------|
| `scout` | `haiku` | low | read-only lookups / symbol searches |
| `Explore` | `haiku` | low | broad read-only search (overrides the built-in search agent) |
| `mech-executor` | `sonnet` | low | fully-specified mechanical work (pattern refactors, convention tests, docs, bulk edits) |
| `executor` | `opus` | medium | judgment work (features, bug fixes) |
| `verifier` | `opus` | medium | fresh-context adversarial check → CONFIRMED / REFUTED |
| `security-executor` | `opus` | high | security-sensitive work (never a cheaper tier) |
| `context-chronicler` | `haiku` | low | session memory compression & token budget checkpointing |
| `compatibility-translator` | `haiku` | low | cross-platform formatting & rule sync (Cursor rules, Antigravity commands) |
| `dependency-guardian` | `opus` | high | package vulnerability & license compliance auditing |

## Delegation rules

- Start at the **cheapest capable role** for the scope; escalate to a richer role only after
  repeated failure (do not pre-escalate).
- Always set an explicit `model` alias when fanning out — never leave it implicit.
- Spec-complete mechanical work → `mech-executor`; work needing judgment → `executor`.

## Re-tiering a role

To move a role to a cheaper or richer model, edit that one role file's `model:` alias in
`configs/claude/agents/<role>.md` (e.g. `opus` → `sonnet`) and re-deploy — one line, one file,
no other role or this policy changes. When a model *version* is superseded, no edit is needed:
the built-in aliases (`haiku`/`sonnet`/`opus`) float to the current version automatically.

## Selective verification (FR-003)

Gate **mutating work, judgment work, and security-sensitive work** behind the `verifier`: the
orchestrator does not proceed until the verifier returns `CONFIRMED`. Pure read-only lookups
(`scout` / `Explore`) MAY skip verification — verifying zero-risk reads only inflates cost and
undercuts the cost-reduction goal. Treat a `REFUTED` verdict as a blocker, not a suggestion.

## Security routing (FR-004 — guardrail)

Security-sensitive work MUST route to `security-executor` and MUST NOT be delegated to the
cheapest tier, even when it looks mechanical. Starter cue set (route to `security-executor` when
the work touches any of these): **authentication/authorization, cryptography, secrets handling,
input validation/sanitization**. This routing is a security control — do not weaken or remove it.

## Cost-reduction target and measurement (SC-001)

The aim of this policy is a **≥40% reduction in model cost** for a mixed session versus running
every unit of work on the frontier model, achieved by routing read-only/mechanical work to
cheaper tiers and reserving the frontier model for planning/decision/review. This is an
aspirational property of the deployed policy, not an enforced gate — Manifest ships **no cost
harness**. To check it manually: run a representative task set once with delegation **off** (all
work on the frontier model) and once with it **on**, comparing the token/cost totals your usage
dashboard reports for the two runs; a well-scoped task mix should show ≥40% lower cost with
delegation on. Verification (selective, below) is the guardrail that keeps the cheaper tiers from
trading cost for correctness.

## Relationship to Manifest's existing facilities (FR-015)

This is a distinct, complementary layer — not a replacement. It does not refactor the
subagent-driven-development skill (which already does per-task model selection) or
`parallel_agent.py` (cross-model consensus). Use those as before; use these roles when you want
named, cost-tiered single-model delegation with a verifier gate.
