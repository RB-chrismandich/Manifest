## 2026-01-27 - Improving CLI Ergonomics
**Learning:** Users often struggle with long paths for internal scripts (`~/.claude/scripts/parallel_agent.sh`). Providing a copy-pasteable alias command during setup significantly reduces friction.
**Action:** Always offer shell aliases for tools installed in non-standard locations. Detect the user's shell to provide the correct command.
