---
max_turns: 15
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Before my AI agents run `gh pr create`, I want `/opt/audit/pr-audit.sh` to run, and if it exits non-zero the PR must not be created. `gh` itself has no hooks system. What's the right way to set this up so it applies to any agent (Claude, Cursor, Codex) that shells out to `gh`? Show me what I'd install.
