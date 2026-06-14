# Phase 1 Data Model: Issue-Linking Git Hooks

The feature is stateless (no database). "Entities" here are the in-memory structures the engine passes between resolution → action → reporting, and the canonical state machine it enforces. Field names are authoritative and MUST match the contracts and tasks.

## Entities

### IssueRef (resolved association)
A linked issue the engine will act on.

| Field | Type | Notes |
|-------|------|-------|
| `number` | int | Issue/MR number on the active platform |
| `source` | enum | How resolved: `branch-prefix` \| `pr-body` \| `commit-message` (inline `#N`/`Fixes #N` refs **and** `Issue:`/`Refs:` trailers) |
| `state` | enum | `open` \| `closed` \| `locked` (from `git_ops.sh issue-view`) |
| `label` | enum\|null | Current canonical status label, or null if unlabeled |
| `exists` | bool | False if a candidate number did not resolve to a real issue |

**Rules**: Only `exists && state == open` issues are mutated (FR-013). Multiple distinct `IssueRef`s per trigger are acted on independently (FR-011). Conflicting candidates → report, do not auto-pick (FR-012).

### TriggerContext
The event that fired a skill.

| Field | Type | Notes |
|-------|------|-------|
| `kind` | enum | `pr-open` \| `commit` |
| `platform` | enum | `github` \| `gitlab` (from `git_platform.sh`); `git`/none → no-op exit |
| `branch` | string | Current branch; its `NNN-` prefix is the primary resolver |
| `pr_number` | int\|null | Set for `pr-open` |
| `commit_sha` | string\|null | Set for `commit` |
| `interactive` | bool | Whether a create-issue prompt can be answered (FR-009) |

### SyncAction (one engine operation + outcome)
| Field | Type | Notes |
|-------|------|-------|
| `type` | enum | `comment` \| `transition` \| `ensure-closing-keyword` \| `create-issue` \| `link` |
| `target` | int\|null | Issue number acted on (null for not-yet-created) |
| `result` | enum | `applied` \| `skipped` \| `failed` |
| `reason` | string | Human-readable why (drives the FR-014 summary) |

### CreatedIssue (best-of-breed creation payload)
| Field | Type | Notes |
|-------|------|-------|
| `title` | string | Derived from branch/PR/commit context |
| `body` | string | Rendered from `references/issue-template.md` — context + acceptance criteria + bidirectional links |
| `labels` | string[] | Canonical; defaults to `["planned"]` |
| `dedup_match` | int\|null | If set, an existing issue was found and reused instead of creating (FR-009a) |

### HookConfig (resolved from command_config.yml)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `hook_timeout_seconds` | int | `5` | Soft timeout bound (R6) |
| `commit_hook_mode` | enum | `sync` | `sync` \| `background` |
| `enabled` | bool | `false` (opt-in) | Per FR-015 |

## State machine — issue status label (forward-only)

Canonical labels from `labels.yml`. Transitions are **monotonic**: the engine never moves an issue backward (FR-006a).

```text
        commit on branch              PR / MR opened              human/CI marks done
   (only if labeled `planned`)
planned ───────────────▶ in-progress ──────────────▶ needs-review ─────────────▶ done
   │                          │                            │
   └── already ≥ target? ─────┴─── no-op (idempotent) ─────┘
```

| Trigger | From | To | Condition |
|---------|------|----|-----------|
| `commit` | `planned` | `in-progress` | issue open AND already labeled `planned`; not already ≥ in-progress. Unlabeled issues are left untouched (outside managed lifecycle, FR-006) |
| `pr-open` | any ≤ in-progress | `needs-review` | issue open; not already ≥ needs-review |
| any | `needs-review` / `done` | — | no-op (already at/after target) |
| any | `closed` / `locked` | — | skip + warn (FR-013) |

`done` is **not** set by these hooks (left to merge/CI/human); shown for completeness.

## Derived dedup keys (no persistence)
- **Transition dedup**: `label >= target` in the ordered set `{planned<in-progress<needs-review<done}`.
- **Comment dedup**: presence of marker `<!-- issue-support:sync v1 pr=<n>|commit=<branch> -->` in existing issue comments (R2).
- **Create dedup**: open-issue title/branch-context match (R4 / FR-009a).

## Validation rules (from requirements)
- A candidate `IssueRef.number` MUST be confirmed via `issue-view` before any mutation (`exists` gate).
- All four `SyncAction.type` mutations MUST be idempotent (FR-007): re-running yields `skipped` with reason "already correct".
- Engine MUST emit the full `SyncAction[]` list as the run summary (FR-014).
- On any failure/timeout, engine exits 0 (fail-open, FR-008) with a `failed`/`skipped` action recorded.
