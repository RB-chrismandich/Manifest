# Shared Skills

This directory is the canonical source of reusable workflows for all supported LLM CLIs.

## Canonical Skills (Transcribed from Commands)

- `checkpoint`
- `docs-diagrams`
- `docs-improve`
- `docs-readme`
- `plan-manage`
- `project-commit`
- `refactor-python`
- `refactor-shell`
- `code-quality` (existing)

## Command Wrappers

- Claude command files in `.claude/commands/` are thin wrappers that delegate to these skills.
- Gemini command files in `.gemini/commands/` are thin wrappers that delegate to these skills.

## Cross-CLI Sharing

- `.gemini/skills` should be symlinked to `.claude/skills`
- `.codex/skills` should be symlinked to `.claude/skills`

This keeps one source of truth and prevents workflow drift.
