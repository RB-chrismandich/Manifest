# Phase 1 Data Model: Command Discovery & Workflow Guidance

**Feature**: 362-command-help-hints | **Date**: 2026-06-21

Entities derived from the spec's Key Entities, plus the supporting `Category` and
`Availability` value objects implied by FR-008/FR-010. All "storage" is files (YAML config
+ generated Markdown + an in-memory catalog); there is no database.

---

## Entity: CommandEntry

One available command, projected from its `SKILL.md`. Built by `command_catalog.py`; never
hand-authored as a second source.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `name` | string (kebab-case) | SKILL.md `name` frontmatter | Unique key. Matches `/name` invocation. |
| `description` | string | SKILL.md `description` frontmatter | Verbatim. |
| `when_to_use` | string | **derived** (D2) | "Use when…" clause → first sentence → humanized name. |
| `category` | enum `Category` | `command_categories.yml` (optional `category:` frontmatter overrides) | Exactly one; defaults to `uncategorized`. |
| `availability` | `Availability` | computed (D6) | Per active context. |

**Validation**:
- `name` MUST be unique across the catalog (duplicate → generation error).
- `category` MUST be a member of the curated taxonomy or `uncategorized` (unknown value → error).
- `description` MUST be non-empty (empty → generation error; flags a malformed skill).

**Relationships**: referenced by zero-or-more `HintRule.command_refs`.

## Value Object: Category

The fixed curated taxonomy (D1).

| Field | Type | Notes |
|-------|------|-------|
| `key` | enum | one of: `git-pr`, `docs`, `security`, `planning`, `skills`, `ci-cd`, `infra`, `meta`, `uncategorized` |
| `label` | string | Human display name for grouping headers. |
| `order` | int | Stable sort order in the discovery listing. |

**Validation**: taxonomy is closed — adding a key is a deliberate `command_categories.yml` edit. `uncategorized` always sorts last.

## Value Object: Availability

| Field | Type | Notes |
|-------|------|-------|
| `service_enabled` | bool | From `services.yml` for the owning service. |
| `deployed_to_platform` | bool | From per-platform deployment mapping for the active agent. |
| `status` | enum `available` \| `unavailable` | `available` iff both booleans true. |
| `reason` | string \| null | When `unavailable`: `"service disabled"` or `"not deployed on <platform>"`. |

## Entity: WorkflowMoment

A recognized point in the user's workflow that can trigger a hint (FR-005, SC-003).

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Stable key, e.g. `pre-commit`, `pr-open`, `refactor-start`, `high-context`. |
| `trigger` | enum | Maps to a hook event (D4): `PreToolUse:git-commit`, `PreToolUse:pr-create`, `command-invoke:refactor-*` (refactor-start), `context-high`. |
| `description` | string | What the moment represents. |

**Validation**: `id` unique; `trigger` MUST resolve to a hook event supported by `ai-hooks-integration`. The registered set of `WorkflowMoment.id`s is the SC-003 evaluation population.

## Entity: HintRule

Maps a WorkflowMoment to the command(s) to surface (the `hint_registry.yml` rows).

| Field | Type | Notes |
|-------|------|-------|
| `moment_id` | ref → WorkflowMoment | The triggering moment. |
| `command_refs` | list<ref → CommandEntry.name> | Command(s) to suggest. |
| `message` | string | One-line hint text (names the command). |
| `priority` | int | Higher wins when multiple rules match one moment (dedup/ordering, FR-006). |
| `dedup_key` | string | Rules sharing a key collapse to one surfaced hint. |
| `category` | enum | `hint` \| `reminder` — selects which opt-out toggle applies. |

**Validation**:
- Every `command_refs` entry MUST resolve to a real `CommandEntry` (dangling ref → registry error).
- A `reminder`-category rule MUST declare a rate-limit window (see GuidancePreference).
- For a given `moment_id`, after dedup by `dedup_key`, surfaced hints are ordered by `priority` desc.

**Relationships**: many HintRule → one WorkflowMoment; HintRule → many CommandEntry.

## Entity: GuidancePreference

User-controlled settings (`guidance.yml`; defaults all-enabled). FR-007 / clarify Q4.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `enabled` | bool | `true` | Global kill-switch; `false` suppresses everything. |
| `categories.hints` | bool | `true` | Per-category toggle. |
| `categories.reminders` | bool | `true` | Per-category toggle. |
| `categories.discovery` | bool | `true` | Gates **proactive** discovery surfacing only (guide injection / unsolicited suggestions). The on-demand `/help` command is always available regardless. |
| `verbosity` | enum `quiet`\|`normal`\|`verbose` | `normal` | Only guidance at/above level is surfaced. |
| `rate_limit.<moment_id>` | duration | per-rule | Min interval between repeats of a moment's reminder. |

**Storage (two layers)**: shipped defaults in committed `configs/claude/config/guidance.yml`; user overrides in gitignored `~/.claude/config/guidance_local.yml`. **Effective value = default ← local override** (local wins per field). A single opt-out toggle writes only the local file (never dirties the tracked tree — SC-004).

**Validation**: a hint/reminder is surfaced **only if** `enabled` AND its `categories.*` toggle is true AND its level ≥ `verbosity` gate AND (for reminders) the rate-limit window has elapsed. Disabling is reliably respected (FR-007, SC-004).

## Runtime state (not committed)

| Item | Location | Notes |
|------|----------|-------|
| `last_fired[moment_id]` | `~/.claude/state/guidance/…` | Timestamps backing the rate-limit window (D5). Machine-local; never in repo. |

---

## State transition — Hint emission (per moment)

```text
moment fires
  → load GuidancePreference
    → enabled == false?            → SUPPRESS
    → category toggle == false?    → SUPPRESS
    → level < verbosity gate?      → SUPPRESS
    → reminder & within window?    → SUPPRESS (rate-limited)
  → collect matching HintRules → dedup by dedup_key → sort by priority
  → emit one-shot hint (transient output; NOT added to always-loaded context)
  → update last_fired[moment_id]
```

## Derived integrity rules (cross-entity)

- **Zero drift (FR-004/SC-002)**: the rendered `docs/COMMANDS.md` MUST equal a fresh render of the catalog; `--check` enforces.
- **No dangling refs**: every `HintRule.command_refs` resolves to a catalog `CommandEntry`.
- **Closed taxonomy**: every `CommandEntry.category` ∈ Category keys.
- **Budget (FR-009/SC-006)**: any catalog content injected into always-loaded guides passes `context_budget`.
