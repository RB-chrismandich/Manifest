---
name: issue-sync-commit
description: |
  Keep the linked GitHub/GitLab issue in sync when commits land on a feature branch:
  advance a planned issue to in-progress, deduplicated across commits. Runs as a
  hook (PostToolUse or native post-commit); fail-open (never blocks the commit).
---

# Commit → Issue Sync Skill

When a commit lands on a feature branch, this skill moves the linked issue into
"active" status so the tracker reflects work-in-progress as soon as it starts. It is
one half of the issue-linking hooks (see also [`issue-sync-pr`]); both delegate to the
shared engine `configs/claude/scripts/issue_support.sh`.

## What it does

For each issue resolved from the commit (branch-number prefix → commit-message
references/trailers):

1. Advances a `planned` issue to `in-progress` (forward-only). Unlabeled issues are
   left untouched — they are outside the managed lifecycle.
2. Posts an idempotent back-link comment, de-duplicated so repeated commits do not
   re-comment or re-transition the same issue.

When no issue resolves, it defers to the missing-issue creation flow (offer on
confirmation; non-interactive → no-create + warning).

**Fail-open**: any error or unreachable tracker degrades to a warning and never blocks
the commit. A timed-out run self-heals on the next commit or a manual re-run.

## Invocation

```bash
configs/claude/scripts/issue_support.sh sync-commit HEAD [--dry-run] [--no-create]
```

## Hook trigger

Installed via `configs/claude/scripts/install_issue_hooks.sh --enable` (unified
`PostToolUse`, matched to `git commit`) and optionally `--native` to add a guarded
git `post-commit` hook for commits made outside an AI tool. Opt-in: gated by
`tool_policies.issue-sync-commit.enabled`.

## Configuration

`command_config.yml → tool_policies.issue-sync-commit`: `enabled` (default false),
`hook_timeout_seconds` (default 5), `commit_hook_mode` (`sync` only in v1;
`background` is reserved and falls back to `sync` with a warning).
