---
name: skill-evolve
description: >-
  Turn SkillClaw's evolved skills into a reviewed PR into .skillshare/skills/.
  Dry-run by default; --apply opens one review PR with one commit per skill.
  Requires SkillClaw enabled (--enable-skillclaw) and the claude CLI logged in.
  Never writes the source of truth directly — every change goes through PR
  review.
---

# Evolve Skills (SkillClaw)

Promote skills SkillClaw has evolved from your Claude Code session transcripts
into the committed `.skillshare/skills/` library — gated behind PR review.

Backed by `~/.claude/scripts/skillclaw_promote.sh`, which ingests your recent
Claude Code transcripts (`~/.claude/projects/**/*.jsonl`), scrubs them of secrets,
evolves `SKILL.md` candidates via `claude -p`, classifies them
(NEW/CHANGED/UNCHANGED), drops any that fail frontmatter checks, and opens one
review PR per batch. No proxy, no daemon — transcripts are read passively.

## When to use

- After a stretch of work, to harvest reusable skills from your recent Claude Code transcripts.
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

- If evolve produces nothing, check that SkillClaw is enabled
  (`./bootstrap.sh --enable-skillclaw`), the `claude` CLI is logged in, and there
  are recent transcripts within the window (`window_days` in
  `~/.claude/config/skillclaw.yml`). Rejected candidates land in
  `~/.skillclaw/skills/rejected/`. Nothing here mutates `.skillshare/skills/`
  without a merged PR.
