---
name: issue-sync-pr
description: "Keep the linked GitHub/GitLab issue in sync when a pull/merge request is opened: back-link comment, advance status label to needs-review, ensure the closing keyword. Runs as a PostToolUse hook; fail-open (never blocks PR creation)."
---

# PR → Issue Sync Skill

When a pull/merge request is opened, this skill updates each issue the PR relates
to so the tracker reflects "up for review" without manual upkeep. It is one half of
the issue-linking hooks (see also [`/manifest-forge:issue-sync-commit`]); both defer to the shared
engine `configs/claude/scripts/issue_support.sh`.

## What it does

For each issue resolved from the PR (branch-number prefix → PR body references →
commit references):

1. Posts an idempotent back-link comment (deduped by a hidden marker).
2. Advances the issue's status label to `needs-review` (forward-only — never regresses).
3. Ensures the PR description contains `Closes #N` (appends it non-destructively if missing).

When no issue resolves, it offers to create a best-of-breed tracking issue
(dedup-checked, templated, `planned`-labeled) — only on confirmation; non-interactive
contexts default to no-create + warning.

**Fail-open**: any error, missing credential, or unreachable tracker degrades to a
single warning and never aborts PR creation. A timed-out run self-heals on re-run.

## Invocation

```bash
# Self-resolves the current branch's PR:
configs/claude/scripts/issue_support.sh sync-pr
# Or target a specific PR:
configs/claude/scripts/issue_support.sh sync-pr 42 [--dry-run] [--no-create]
```

`--dry-run` previews actions without mutating; `--no-create` suppresses the
missing-issue creation offer.

## Hook trigger

Installed as a unified `PostToolUse` hook (cross-tool) via
`configs/claude/scripts/install_issue_hooks.sh --enable`, matched to PR/MR-create
commands. Opt-in: gated by `tool_policies.issue-sync-pr.enabled` in
`command_config.yml`. Coverage boundary: PR creation via the web UI or raw
`gh`/`glab` outside a tool is not auto-observed — run `sync-pr` manually there.

## Configuration

`command_config.yml → tool_policies.issue-sync-pr`: `enabled` (default false),
`hook_timeout_seconds` (default 5).
