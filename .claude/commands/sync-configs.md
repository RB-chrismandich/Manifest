---
description: Verify cross-platform config consistency, symlinks, and detect drift
allowed-tools: Bash, Read, Glob, Grep
argument-hint: [platform (optional)]
---

# Sync Configs Command

Use the shared skill workflow as the source of truth.

- Skill path: `~/.claude/skills/sync-configs/SKILL.md`
- Canonical repo path: `.claude/skills/sync-configs/SKILL.md`

## Execution

Read the skill file and follow its instructions. If `$ARGUMENTS` specifies a
platform (e.g., "cursor", "gemini", "codex"), check only that platform.
Otherwise check all platforms.
