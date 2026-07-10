---
name: deploy-reconcile
description: Review what Manifest deployed into the assistant homes (~/.claude + mirrors) versus what the project would deploy, listing orphaned deployed items KEEP or REMOVE. Preview by default; opt-in removal is recoverable (timestamped backup, never hard-delete).
---

# Deploy Reconciliation Review

Find deployed units (skills, config files, scripts) that exist in your home but no longer
exist in the project, and reconcile them. Preview is the default and changes
nothing; removal is explicit, recoverable, and never runs during a routine deploy.

Backed by `~/.claude/scripts/deploy_reconcile.sh`. The protection policy lives in
`~/.claude/config/reconcile.yml` (source: `configs/claude/config/reconcile.yml`),
with machine-local additions in `~/.manifest/reconcile.local.yml`.

## When to use

- After deleting or renaming skills/config in the repo, to find leftovers still
  deployed in your home.
- To audit drift between the repo and your deployed `~/.claude` (and the mirrored
  assistant homes) without changing anything.
- To safely clean up orphaned deployed files, with a recoverable backup.

Related but different: `config-audit`/`env-check` check cross-platform drift and
symlink integrity (read-only); `deploy-diagnose-drift` finds state *missing* from
a deploy. This skill finds state that is *extra*/orphaned and can prune it.

## Task

1. **Preview first** (default — reads only, deletes nothing):

   ```bash
   ~/.claude/scripts/deploy_reconcile.sh --project <repo-root>
   ```

   Output lists KEEP items (with the protection reason or active dependent) first,
   then REMOVE orphans, then a one-line summary. Shared symlinked targets are
   resolved and reported once. Use `--json` for machine-readable output.

   - `--project DIR` (or `MANIFEST_REPO`) is the repo source of truth. The deployed
     `~/.claude/scripts` copy has no repo, so pass it explicitly (exit 2 otherwise).

2. **Apply, with confirmation** (only on explicit user request):

   ```bash
   # Move REMOVE orphans to a recoverable backup (prompts to confirm)
   ~/.claude/scripts/deploy_reconcile.sh --project <repo-root> --remove

   # Non-interactive (automation):
   ~/.claude/scripts/deploy_reconcile.sh --project <repo-root> --remove --yes
   ```

   KEEP items are never touched. Removed items are *moved* to
   `~/.manifest/reconcile-trash/<timestamp>/` with a generated `restore.sh`.

3. **Review the outcome.** Confirm the reported backup path, that KEEP/shared items
   remain in place, and that `removed.tsv` lists what moved. Restore anything with
   the generated `~/.manifest/reconcile-trash/<timestamp>/restore.sh`.

## Safety

- Preview-first and non-destructive by default (SC-002).
- Removal is recoverable (move-aside, not delete) and requires `--remove` plus a
  confirmation or `--yes`.
- Never run `--remove` as part of a routine deploy — the deploy-time review is
  report-only by design (FR-006).
- Protect extra paths via `--protect GLOB` or `~/.manifest/reconcile.local.yml`.
