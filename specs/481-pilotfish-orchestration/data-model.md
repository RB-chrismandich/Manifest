# Phase 1 Data Model: Pilotfish-Style Cost-Tiered Model Orchestration

This feature is config-only; the "data model" is the set of configuration entities the
integration deploys and the relationships/validation rules between them. No runtime schema, DB,
or serialized state beyond Markdown/YAML config.

## Entity 1 — Role Agent

A named, config-only unit of delegatable work. One Markdown file per role in
`configs/claude/agents/<name>.md` (deployed to `~/.claude/agents/<name>.md`).

| Field | Type | Rules |
|-------|------|-------|
| `name` | string (frontmatter) | Unique across the set; matches the filename stem. Six fixed names: `scout`, `Explore`, `mech-executor`, `executor`, `verifier`, `security-executor`. |
| `description` | string (frontmatter) | When-to-delegate trigger text for the orchestrator. |
| `model` | built-in alias | One of `haiku`\|`sonnet`\|`opus` (see Entity 2). Never a raw model ID (FR-002), unless a documented per-role pin override is required. |
| `effort` | enum | `low`\|`medium`\|`high`. Per R2: scout/Explore/mech=low; executor/verifier=medium; security-executor=high. |
| body | Markdown | Role instructions (scope, output contract; verifier returns CONFIRMED/REFUTED). |

**Relationships**: each Role Agent names exactly one Model Alias (Entity 2) and is governed by
the Delegation Policy (Entity 3).

**Validation**:
- The set MUST contain exactly the six named roles (FR-001).
- `Explore` overrides the built-in search agent and MUST be bound to `haiku` (clarify Q4).
- `security-executor` MUST be bound to `opus` (FR-004); it MUST NOT be `sonnet`/`haiku`.
- Deployment MUST abort if a target filename already exists un-owned (FR-008; Entity 4).

## Entity 2 — Model Alias

Claude Code's built-in model aliases, named directly in each role's frontmatter `model:` field.
No custom alias-definition file is deployed — Claude Code resolves these natively, and they
float to the current model version (the single reason no machine-readable alias source or
`settings.json` change is needed; see research R2/R7).

| Alias | Resolves to (current) | Cost intent | Roles |
|-------|-----------------------|-------------|-------|
| `opus` | Opus 4.8 (`claude-opus-4-8`) | high | executor, verifier, security-executor |
| `sonnet` | Sonnet 5 (`claude-sonnet-5`) | mid | mech-executor |
| `haiku` | Haiku 4.5 (`claude-haiku-4-5-20251001`) | cheap | scout, Explore |

The "frontier"/orchestrator model is the **unchanged main session** (FR-016) — not a deployed
alias; pilotfish's Layer-1 `best` alias is deliberately not adopted (clarify Q1).

**Validation**:
- Every alias named by a Role Agent MUST be a built-in Claude Code alias (`haiku`/`sonnet`/
  `opus`) or a documented per-role pin override (FR-002).
- Model availability/fallback is handled by Claude Code (FR-007) — no custom fallback chain is
  deployed.

**State transition**: a model version is superseded → Claude Code repoints the built-in alias
automatically → roles follow with **zero** Manifest edits. Re-tiering a role → edit that one
role's `model:` alias (one line, one file) → redeploy (US2/SC-002).

## Entity 3 — Delegation Policy

The orchestrator-facing rules, deployed as a **read-on-demand** reference at
`configs/claude/references/pilotfish-delegation.md` → `~/.claude/references/`. Pointed to (not
inlined) from `configs/claude/CLAUDE.md`'s Reference Index (FR-014, budget-safe).

**Contents**:
- The role → alias → effort table (Entities 1–2), noting what each built-in alias currently
  resolves to.
- Delegation rules: start at the cheapest capable role; escalate after repeated failure.
- **Selective verification** rule: gate mutating, judgment, and security work behind the
  `verifier`; MAY skip pure read-only lookups (scout/Explore) (FR-003, clarify Q2).
- Security-routing rule: security-sensitive work → `security-executor`, never the cheapest
  tier (FR-004); starter cue set = auth/crypto/secrets/input-validation (R-open-item).
- Upstream attribution + vendored version (pilotfish v1.1.0, MIT) (FR-011).

**Validation**: the always-loaded pointer keeps `configs/claude/CLAUDE.md` under its budget cap
(FR-009); the full policy carries no context cost until read.

## Entity 4 — Service Toggle

The enable/disable state, in generated `services.yml` (`pilotfish.enabled`), honored by
deployment.

| Field | Type | Rules |
|-------|------|-------|
| `pilotfish.enabled` | bool | Default `false` (opt-in; skillclaw pattern, R1). Set by `--enable-pilotfish`/`--disable-pilotfish`. |

**State transitions**:
- `false → true` (enable + redeploy): deploy the six Role Agents + the Delegation Policy
  reference + the guide pointer; abort on collision (FR-008).
- `true → false` (disable + redeploy): remove exactly those artifacts, nothing else (SC-003).

**Validation**: enable→disable returns `~/.claude/` to a state diff-identical to never-enabled
(SC-003); reconcile treats the deployed agents dir as owned when enabled, prunes it when
disabled (R6).
