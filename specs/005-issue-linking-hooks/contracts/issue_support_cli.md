# Contract: `issue_support.sh` (shared engine CLI)

Platform-agnostic engine, sibling to `git_ops.sh`. Bash, `set -euo pipefail`, `err()` for diagnostics, `--help` ≤15 lines. **Fail-open**: every user-facing subcommand exits `0` even on internal failure (a non-zero exit is reserved for usage errors only).

## Subcommands

### `issue_support.sh sync-pr <PR_NUMBER> [--dry-run] [--no-create]`
Run the full PR-trigger flow for an opened PR/MR.
- Resolves `IssueRef[]` (R3), advances each open issue to `needs-review`, posts/refreshes the marker back-link comment, ensures `Closes #N` in the PR body.
- No linked issue → offer best-of-breed creation (unless `--no-create` or non-interactive).
- **Exit**: `0` always (fail-open). `--dry-run` prints planned `SyncAction[]` without mutating.

### `issue_support.sh sync-commit <SHA|HEAD> [--dry-run] [--no-create]`
Run the commit-trigger flow.
- Resolves `IssueRef[]`, advances each open issue already labeled `planned` to `in-progress` (unlabeled issues left untouched, FR-006), dedup-guards the comment.
- Respects `commit_hook_mode`; in `background` mode returns immediately and detaches the work.
- **Exit**: `0` always.

### `issue_support.sh resolve <--pr N | --commit SHA | --branch NAME>`
Resolution-only (no mutation). Prints resolved `IssueRef[]` as JSON. Used by tests and `--dry-run`. **Exit**: `0` on success, `3` if no issue resolved (informational, still non-fatal to callers that ignore it).

### `issue_support.sh --help`
Usage + flags, exit `0`.

## Inputs / environment
| Input | Source |
|-------|--------|
| Active platform | `git_platform.sh` (or `MANIFEST_GIT_PLATFORM`) |
| Tracker operations | `git_ops.sh issue-view/issue-list/issue-comment/issue-comment-edit-last/issue-edit/issue-create/pr-view` |
| PR-body write (closing keyword) | `git_ops.sh pr-edit <N>` — **new** thin wrapper (`gh pr edit --body` / `glab mr update --description`); appends `Closes #N` non-destructively when missing. Absent/failed → warn-only (C1 fail-open) |
| Canonical labels | `labels.yml` |
| Created-issue template | `configs/claude/scripts/templates/issue_support_issue.md` (engine-relative path; identical for both skills) |
| `hook_timeout_seconds`, `commit_hook_mode`, `enabled` | `command_config.yml` → `tool_policies.{pr-issue-sync,commit-issue-sync}` |

## Output contract (stdout)
Human-readable summary, one line per `SyncAction`:
```text
issue-support: #17 transition planned→needs-review [applied]
issue-support: #17 comment back-link [skipped] (marker already present)
issue-support: PR body closing-keyword Closes #17 [applied]
```
`--dry-run` prefixes each line with `(dry-run)`. JSON form available via `resolve` and `--json`.

## Behavioral guarantees (testable)
| ID | Guarantee | Maps to |
|----|-----------|---------|
| C1 | Never exits non-zero from `sync-pr`/`sync-commit`, even when `git_ops.sh` fails or times out | FR-008, SC-002 |
| C2 | Re-running against an already-correct issue produces only `skipped` actions | FR-007, SC-003 |
| C3 | Resolution precedence is branch-prefix → pr-body → commit-message (inline refs + trailers); unresolved prefix falls through | R3, FR-004 |
| C4 | Closed/locked issues are skipped with a warning, never mutated | FR-013 |
| C5 | Forward-only transitions; an issue at `needs-review` is never moved back to `in-progress` | FR-006a |
| C6 | `--no-create` and non-interactive both suppress issue creation | FR-009 |
| C7 | Multiple resolved issues are each acted on; ambiguous conflicts reported not auto-picked | FR-011, FR-012 |
