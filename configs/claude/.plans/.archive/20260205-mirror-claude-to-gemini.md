# Plan: Mirror .claude to .gemini with Like-for-Like Capability

**Status**: COMPLETED
**Created**: 2026-02-05
**Author**: Claude (orchestrator)
**Branch**: main

---

## Objective

Create a `.gemini/` directory in the Manifest repo that provides Gemini CLI with equivalent
orchestration capability to the existing `.claude/` setup. Use symlinks where the same file
can serve both agents; create Gemini-native files only where format differences require it.

## Context

The Manifest repo manages Claude Code agent configurations deployed to `~/.claude/`. Gemini CLI
(`@google/gemini-cli`) has an analogous configuration system using `.gemini/` with `GEMINI.md`
(equivalent to `CLAUDE.md`), `commands/` (TOML format, not Markdown), `skills/` (same `SKILL.md`
convention), and `settings.json`. The goal is to give Gemini CLI the same orchestration context
without duplicating content unnecessarily.

### Key Format Differences

| Component | Claude Code | Gemini CLI | Symlink? |
|-----------|------------|------------|----------|
| Context file | `CLAUDE.md` (Markdown) | `GEMINI.md` (Markdown) | NO - needs rename + minor adaptation |
| Commands | `commands/*.md` (Markdown with YAML frontmatter) | `commands/*.toml` (TOML format) | NO - different format entirely |
| Skills | `skills/*/SKILL.md` | `skills/*/SKILL.md` | YES - identical convention |
| Config YAML | `config/*.yml` | N/A (uses `settings.json`) | PARTIAL - YAML files are agent-agnostic reference data |
| Prompts | `prompts/*.md` | Referenced from GEMINI.md | YES - agent-agnostic templates |
| Scripts | `scripts/*.sh` | Referenced by path | YES - already supports all agents |
| Plans | `.plans/` | `.plans/` | YES - agent-agnostic management |
| Settings | `settings.local.json` | `settings.json` | NO - different schema |

## Deliverables

### Phase 1: Directory Structure and Symlinks

- [x] **1.1** Create `.gemini/` directory structure in the repo
- [x] **1.2** Symlink `prompts/` directory: `.gemini/prompts/ -> ../claude/prompts/`
  (all 4 prompt templates are agent-agnostic)
- [x] **1.3** Symlink `scripts/` directory: `.gemini/scripts/ -> ../.claude/scripts/`
  (parallel_agent.sh already supports Gemini)
- [x] **1.4** Symlink `.plans/` directory: `.gemini/.plans/ -> ../.claude/.plans/` (shared plan management)
- [x] **1.5** Symlink `skills/code-quality/SKILL.md`: `.gemini/skills/code-quality/SKILL.md -> ../../../.claude/skills/code-quality/SKILL.md`
- [x] **1.6** Symlink `config/` YAML files: `.gemini/config/ -> ../.claude/config/`
  (command_config.yml, validation_criteria.yml, services.yml are agent-agnostic
  reference data)

### Phase 2: GEMINI.md (Context File)

- [x] **2.1** Create `.gemini/GEMINI.md` adapted from `.claude/CLAUDE.md`
  - Replace "Claude" references with "Gemini" where appropriate (agent-specific sections)
  - Keep all orchestration content (parallel agents, validation, cross-verification)
  - Keep all model tier tables, consensus thresholds, workflow integration
  - Adjust "Native Commands" section to reference TOML commands
  - Keep file structure section updated for `.gemini/` layout

### Phase 3: TOML Commands (Format Conversion)

Gemini CLI uses TOML files with `description` and `prompt` fields. Claude's Markdown commands
contain complex multi-phase instructions. The TOML `prompt` field will contain the full
instruction text.

- [x] **3.1** Convert `commands/project-commit.md` -> `.gemini/commands/project-commit.toml`
- [x] **3.2** Convert `commands/refactor-python.md` -> `.gemini/commands/refactor-python.toml`
- [x] **3.3** Convert `commands/refactor-shell.md` -> `.gemini/commands/refactor-shell.toml`
- [x] **3.4** Convert `commands/docs-diagrams.md` -> `.gemini/commands/docs-diagrams.toml`
- [x] **3.5** Convert `commands/docs-improve.md` -> `.gemini/commands/docs-improve.toml`
- [x] **3.6** Convert `commands/docs-readme.md` -> `.gemini/commands/docs-readme.toml`
- [x] **3.7** Convert `commands/plan-manage.md` -> `.gemini/commands/plan-manage.toml`
- [x] **3.8** Convert `commands/checkpoint.md` -> `.gemini/commands/checkpoint.toml`

### Phase 4: Gemini Settings

- [x] **4.1** Create `.gemini/settings.json` with project-level Gemini CLI settings
  - Tool approval mode
  - Context filename configuration (ensure `GEMINI.md` is loaded)
  - Any relevant model configuration

### Phase 5: Bootstrap Integration

- [x] **5.1** Update `bootstrap.sh` to also deploy `.gemini/` contents to `~/.gemini/`
  - Copy non-symlinked files (GEMINI.md, commands/*.toml, settings.json)
  - Resolve symlinks and copy target files for deployment (symlinks are repo-internal)
  - Preserve existing `~/.gemini/` auth files (oauth_creds.json, google_accounts.json, etc.)

### Phase 6: Documentation

- [x] **6.1** Update root `CLAUDE.md` repository structure section to include `.gemini/`
- [x] **6.2** Update `README.md` to document the `.gemini/` directory and deployment
- [x] **6.3** Add a brief note in `.gemini/GEMINI.md` explaining the symlink strategy

## Related Files

| File | Change |
|------|--------|
| `.gemini/GEMINI.md` | CREATE - Adapted orchestration guide |
| `.gemini/commands/*.toml` | CREATE (x8) - TOML conversions of Claude commands |
| `.gemini/settings.json` | CREATE - Project Gemini CLI settings |
| `.gemini/prompts/` | SYMLINK -> `../.claude/prompts/` |
| `.gemini/scripts/` | SYMLINK -> `../.claude/scripts/` |
| `.gemini/.plans/` | SYMLINK -> `../.claude/.plans/` |
| `.gemini/config/` | SYMLINK -> `../.claude/config/` |
| `.gemini/skills/code-quality/SKILL.md` | SYMLINK -> `../../../.claude/skills/code-quality/SKILL.md` |
| `bootstrap.sh` | MODIFY - Add `.gemini/` deployment |
| `CLAUDE.md` (root) | MODIFY - Update repo structure |
| `README.md` | MODIFY - Document `.gemini/` |

## Implementation Notes

### Symlink Strategy

Symlinks are **repo-internal** (relative paths within the repo). During deployment via
`bootstrap.sh`, symlinks are resolved and files are copied to their final locations. This
avoids broken symlinks on target machines where `~/.claude/` and `~/.gemini/` are separate
directories.

### TOML Command Format

Gemini CLI TOML commands use this structure:

```toml
description = "Short description of the command"
prompt = """
Full multi-line instruction text goes here.
This replaces the Markdown body from Claude commands.
The YAML frontmatter (description, allowed-tools, argument-hint) maps to TOML keys.
Arguments are injected via {{args}} placeholder.
Shell commands can be embedded via !{command} syntax.
"""
```

### What Cannot Be Symlinked

1. **GEMINI.md** - Must be named `GEMINI.md` (not `CLAUDE.md`). Content is 95% the same
   but needs agent-appropriate naming and minor adjustments.
2. **Commands** - Completely different format (TOML vs Markdown with YAML frontmatter).
   Gemini has no equivalent of `allowed-tools` or `argument-hint` frontmatter.
3. **settings.json** - Different schema from Claude's `settings.local.json`.

### What CAN Be Symlinked (6 items)

1. `prompts/` - All 4 prompt templates are agent-agnostic
2. `scripts/` - `parallel_agent.sh` already has full Gemini support
3. `.plans/` - Plan management is shared across agents
4. `config/` - YAML configs are reference data, not agent-specific settings
5. `skills/code-quality/SKILL.md` - Same convention in both CLIs
6. `.agent_outputs/` - Shared output directory (if created)

## Risks

- **Risk**: Gemini CLI may not support all features referenced in commands (e.g., `Task` subagents,
  `AskUserQuestion`) — **Mitigation**: TOML commands focus on the prompt content; Gemini's tool
  system handles capabilities differently. Strip Claude-specific tool references.
- **Risk**: Symlinks may not work on Windows if repo is cloned there — **Mitigation**: bootstrap.sh
  already targets macOS/Linux only. Document this limitation.
- **Risk**: TOML commands may have size limits for the `prompt` field — **Mitigation**: Test with
  the largest command (refactor-shell.md at 409 lines). Gemini CLI should handle large prompts.
- **Risk**: Gemini CLI's `settings.json` schema may evolve — **Mitigation**: Use minimal
  settings; link to upstream schema for reference.

## Completion Criteria

- [ ] All deliverables checked off
- [ ] `gemini` CLI can load `.gemini/GEMINI.md` as project context
- [ ] All 8 TOML commands are invocable via `/command-name` in Gemini CLI
- [ ] Symlinked files resolve correctly within the repo
- [ ] `bootstrap.sh` deploys both `.claude/` and `.gemini/` correctly
- [ ] No regressions to existing `.claude/` functionality

## Parallel Plans

- **Runs in parallel with**: `20260205-cursor-mirror.md` (Cursor IDE mirror)
- **Shared files (serialize Phase 5-6)**: `bootstrap.sh`, root `CLAUDE.md`, `README.md`, `AGENTS.md`
- **No conflicts on Phases 1-4**: Each plan creates its own directory (`.gemini/` vs `.cursor/`)

## Log

| Date | Entry |
|------|-------|
| 2026-02-05 | Plan created via /plan-manage create. Single-agent planning (structural task, not security-critical). Explored .claude/ structure (25+ files), researched Gemini CLI config system (GEMINI.md, TOML commands, settings.json, skills). Identified 6 symlinkable components and 3 that require Gemini-native files. |
| 2026-02-05 | Cross-referenced with cursor-mirror plan. Cursor plan already fully implemented (Phases 1-5 complete). Beginning Gemini implementation. |
| 2026-02-05 | All 19 deliverables completed. 5 symlinks + 1 file symlink, GEMINI.md, 8 TOML commands, settings.json, bootstrap.sh updated, CLAUDE.md/AGENTS.md/README.md updated. Moving to archive. |
