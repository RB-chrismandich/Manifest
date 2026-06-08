---
name: skill-evolve
description: |
  Turn SkillClaw's evolved skills into a reviewed PR into .skillshare/skills/.
  Dry-run by default (shows the diff table and makes no changes); --apply opens a
  single review PR with one commit per skill. Requires the SkillClaw daemon
  (enable via ./bootstrap.sh --enable-skillclaw). Never writes to the source of
  truth directly — every change goes through PR review.
---

# Evolve Skills (SkillClaw)

Promote skills SkillClaw has evolved from captured CLI-agent sessions into the
committed `.skillshare/skills/` library — gated behind PR review.

Backed by `~/.claude/scripts/skillclaw_promote.sh`, which classifies evolved
skills (NEW/CHANGED/UNCHANGED), drops any that fail `verify`/frontmatter checks,
scrubs captured sessions of secrets, and opens one review PR per batch.

## When to use

- After a stretch of work captured by the SkillClaw proxy, to harvest refined skills.
- To review what SkillClaw would propose before committing anything (dry-run).

## Task

1. **Preview (dry-run, default — makes no changes):**

   ```bash
   ~/.claude/scripts/skillclaw_promote.sh --no-evolve
   ```

   Prints the candidate table (NEW / CHANGED / DROPPED + reason). Use `--no-evolve`
   to classify the existing evolved library without re-running evolution.

2. **Evolve fresh, then preview:**

   ```bash
   ~/.claude/scripts/skillclaw_promote.sh
   ```

3. **Open the review PR (one PR, one commit per skill):**

   ```bash
   ~/.claude/scripts/skillclaw_promote.sh --apply
   ```

   Aborts if an open `skillclaw/evolve-*` PR already exists — review/merge that
   first, or pass `--force-new`. Scope to one skill with `--skill <name>`.

4. **Review the PR** like any other: each skill is its own commit; revert a commit
   to drop a single skill. Merge to deploy via the normal `bootstrap.sh` skill sync.

## Notes

- If the daemon is down, capture simply didn't happen — fix it with
  `/health-check` then `./bootstrap.sh --enable-skillclaw`. Nothing here mutates
  `.skillshare/skills/` without a merged PR.
