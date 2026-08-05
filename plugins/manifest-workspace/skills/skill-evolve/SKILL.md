---
name: skill-evolve
description: Use after a stretch of work to harvest SkillClaw-evolved skills from Claude Code session transcripts into a reviewed PR against .apm/skills/. Dry-run by default; requires --enable-skillclaw and claude CLI login. Never writes source of truth directly.
---

# Evolve Skills (SkillClaw)

Promote skills SkillClaw has evolved from your Claude Code session transcripts
into the committed `.apm/skills/` library — gated behind PR review.

Backed by `~/.claude/scripts/skillclaw_promote.sh`, which ingests your recent
Claude Code transcripts (`~/.claude/projects/**/*.jsonl`), scrubs them of secrets,
evolves `SKILL.md` candidates via `"${EVOLVE_CLI}" -p`, classifies them
(NEW/CHANGED/UNCHANGED), drops any that fail frontmatter checks, and opens one
review PR per batch. No proxy, no daemon — transcripts are read passively.

## LLM CLI seam

The distillation step shells out to `EVOLVE_CLI="${EVOLVE_CLI:-claude}" -p`
(`configs/claude/scripts/skillclaw_evolve.py`, `subprocess_runner()`) — a
role-named, injectable seam per the `/manifest-code-quality:llm-invoke-stdin` pattern. Swapping
vendors (`claude` -> `gemini`, `agy`, etc.) is a one-line env-var change:

```bash
EVOLVE_CLI=gemini ~/.claude/scripts/skillclaw_promote.sh
```

**Not swappable — by design, not an oversight:** the *data source* this step
distills from is `~/.claude/projects/**/*.jsonl` — Claude Code's own session
transcript format, read by `skillclaw_ingest.py`. That format is inherent to
running inside Claude Code; it is not a CLI choice, so `EVOLVE_CLI` only
changes which model does the distilling, never where the sessions come from.
Running this skill from a non-Claude-Code harness has no transcripts to read,
regardless of `EVOLVE_CLI`.

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
  `~/.skillclaw/skills/rejected/`. Nothing here mutates `.apm/skills/`
  without a merged PR.
