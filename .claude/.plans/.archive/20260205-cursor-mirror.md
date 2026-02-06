# Plan: Mirror .claude Configuration for Cursor IDE

**Status**: ACTIVE
**Created**: 2026-02-05
**Author**: Claude (orchestrated with Gemini)
**Branch**: feat/cursor-mirror

---

## Objective

Create a `.cursor/` directory that provides like-for-like capability with the existing `.claude/`
configuration, using symlinks for shared assets and adapted copies only where platform differences
require it.

## Context

The Manifest repository manages Claude Code agent configurations deployed to `~/.claude/`. Cursor
IDE has a compatible but distinct configuration format: `.cursor/rules/*.mdc` (rules with YAML
frontmatter), `.cursor/commands/*.md` (same format as Claude), and `AGENTS.md` (project
instructions). The goal is to ensure developers using Cursor get the same orchestration
capabilities — parallel agent review, code quality checks, plan management — without maintaining
duplicate configuration.

**Key format differences discovered:**

- Cursor rules use `.mdc` with `description`, `globs`, `alwaysApply` frontmatter
- Claude commands use `.md` with `description`, `allowed-tools`, `argument-hint` frontmatter
- Commands referencing Claude-only tools (Task, Skill, AskUserQuestion) need Cursor equivalents
- Scripts, configs, prompts, and plans are fully platform-agnostic

## Deliverables

### Phase 1: Directory Structure & Symlinks

- [x] **1.1** Create `.cursor/` directory with subdirectories
- [x] **1.2** Symlink `.cursor/scripts/` → `../.claude/scripts/` (bash scripts are generic)
- [x] **1.3** Symlink `.cursor/config/` → `../.claude/config/` (YAML configs are generic)
- [x] **1.4** Symlink `.cursor/prompts/` → `../.claude/prompts/` (agent templates are generic)
- [x] **1.5** Symlink `.cursor/.plans/` → `../.claude/.plans/` (markdown plans are generic)

### Phase 2: Cursor-Specific Rules (adapted from commands/skills)

- [x] **2.1** Create `.cursor/rules/orchestration.mdc` — always-on rule adapted from `.claude/CLAUDE.md`
- [x] **2.2** Create `.cursor/rules/code-quality.mdc` — auto-triggered rule adapted from `.claude/skills/code-quality/SKILL.md`
- [x] **2.3** Create `.cursor/rules/refactor-python.mdc` — adapted from `refactor-python.md` command
- [x] **2.4** Create `.cursor/rules/refactor-shell.mdc` — adapted from `refactor-shell.md` command
- [x] **2.5** Create `.cursor/rules/docs-readme.mdc` — adapted from `docs-readme.md` command
- [x] **2.6** Create `.cursor/rules/docs-improve.mdc` — adapted from `docs-improve.md` command
- [x] **2.7** Create `.cursor/rules/docs-diagrams.mdc` — adapted from `docs-diagrams.md` command
- [x] **2.8** Create `.cursor/rules/project-commit.mdc` — adapted from `project-commit.md` command
- [x] **2.9** Create `.cursor/rules/plan-manage.mdc` — adapted from `plan-manage.md` command

### Phase 3: AGENTS.md (Project Instructions)

- [x] **3.1** Create `AGENTS.md` in project root — AI agent instructions for all platforms

### Phase 4: Bootstrap Integration

- [x] **4.1** Update `bootstrap.sh` to deploy `.cursor/` alongside `.claude/` (auto-deploys with rules + symlinks)
- [x] **4.2** ~~Add `--enable-cursor-config` / `--disable-cursor-config` flags~~
  — Simplified: Cursor config always deploys alongside Claude
  (no separate toggle needed since it's lightweight)

### Phase 5: Documentation

- [x] **5.1** Update `CLAUDE.md` (project root) to document the `.cursor/` mirror
- [x] **5.2** Update `README.md` to mention Cursor compatibility

## Related Files

| File | Change |
|------|--------|
| `.cursor/` (new dir) | Create entire directory structure |
| `.cursor/scripts` | Symlink → `../.claude/scripts/` |
| `.cursor/config` | Symlink → `../.claude/config/` |
| `.cursor/prompts` | Symlink → `../.claude/prompts/` |
| `.cursor/.plans` | Symlink → `../.claude/.plans/` |
| `.cursor/rules/orchestration.mdc` | New file — adapted from `.claude/CLAUDE.md` |
| `.cursor/rules/code-quality.mdc` | New file — adapted from `.claude/skills/code-quality/SKILL.md` |
| `.cursor/rules/refactor-python.mdc` | New file — adapted from `.claude/commands/refactor-python.md` |
| `.cursor/rules/refactor-shell.mdc` | New file — adapted from `.claude/commands/refactor-shell.md` |
| `.cursor/rules/docs-readme.mdc` | New file — adapted from `.claude/commands/docs-readme.md` |
| `.cursor/rules/docs-improve.mdc` | New file — adapted from `.claude/commands/docs-improve.md` |
| `.cursor/rules/docs-diagrams.mdc` | New file — adapted from `.claude/commands/docs-diagrams.md` |
| `.cursor/rules/project-commit.mdc` | New file — adapted from `.claude/commands/project-commit.md` |
| `.cursor/rules/plan-manage.mdc` | New file — adapted from `.claude/commands/plan-manage.md` |
| `AGENTS.md` | New file — project instructions for Cursor |
| `bootstrap.sh` | Add `.cursor/` deployment support |
| `CLAUDE.md` (project root) | Document `.cursor/` mirror |
| `README.md` | Mention Cursor compatibility |

## Implementation Notes

### Symlink Strategy (5 directories)

All symlinks use **relative paths** for portability across machines:

```bash
ln -s ../.claude/scripts .cursor/scripts
ln -s ../.claude/config .cursor/config
ln -s ../.claude/prompts .cursor/prompts
ln -s ../.claude/.plans .cursor/.plans
```

### Why Commands Cannot Be Symlinked

Claude commands use `allowed-tools` frontmatter referencing Claude-specific tools:

- `Task` (spawn subagents) → Cursor has no direct equivalent
- `Skill` (invoke skills) → Cursor uses rules auto-attachment instead
- `AskUserQuestion` → Cursor has built-in user prompting

The **body content** (instructions, workflows) is largely reusable, but must be adapted to
Cursor's `.mdc` format with `description`, `globs`, and `alwaysApply` frontmatter.

### .mdc Adaptation Pattern

Each command → rule conversion follows this pattern:

```yaml
# Claude command frontmatter:
---
description: Analyze Python codebase for security
allowed-tools: Read, Glob, Grep
argument-hint: [file-or-directory]
---

# Cursor rule frontmatter:
---
description: "Analyze Python codebase for security, architecture, and code quality"
globs: "**/*.py"
alwaysApply: false
---
```

The body text is preserved with minor adjustments:

- Replace "Task(subagent_type: ...)" references with terminal command equivalents
- Replace "Skill" invocations with `@rule-name` references
- Keep `parallel_agent.sh` calls unchanged (they work from terminal in both IDEs)

### Excluded from Mirror

- `.claude/settings.local.json` — Claude Code permission system (no Cursor equivalent)
- `.claude/commands/checkpoint.md` — Claude-specific context management (200K window tracking)
- `.claude/prompts/context_monitor.md` — Claude-specific context auto-trigger

## Risks

- **Frontmatter incompatibility**: Claude `allowed-tools` vs Cursor `globs`/`alwaysApply`
  — **Mitigation**: Adapted copies with proper Cursor frontmatter
- **Tool name drift**: Cursor may update its tool/rule format
  — **Mitigation**: Version-pin the `.mdc` format and test with Cursor before deploying
- **Symlink portability**: Windows Git may not handle symlinks
  — **Mitigation**: Document `git config core.symlinks true` requirement;
  bootstrap script handles platform differences
- **Dual maintenance**: Rule body content could drift from command body
  — **Mitigation**: Add comments in each `.mdc` file noting the source
  `.claude/commands/*.md` file for manual sync

## Completion Criteria

- [ ] All deliverables checked off
- [ ] `.cursor/` directory exists with correct symlinks (verified via `ls -la`)
- [ ] All `.mdc` rules have valid YAML frontmatter
- [ ] Symlinks resolve correctly (`readlink` verification)
- [ ] `bootstrap.sh` can deploy `.cursor/` config
- [ ] AGENTS.md exists at project root
- [ ] No regressions to existing `.claude/` configuration

## Parallel Plans

- **Runs in parallel with**: `20260205-mirror-claude-to-gemini.md` (Gemini CLI mirror)
- **Shared files (serialize Phase 4-5)**: `bootstrap.sh`, root `CLAUDE.md`, `README.md`
- **No conflicts on Phases 1-3**: Each plan creates its own directory (`.cursor/` vs `.gemini/`)

## Log

| Date | Entry |
|------|-------|
| 2026-02-05 | Plan created. Parallel agents: Gemini only (Cursor CLI missing, Claude CLI disabled with --no-claude). Synthesized with Explore agent codebase analysis and Cursor docs research. |
| 2026-02-05 | All deliverables completed. 4 symlinks, 9 .mdc rules, AGENTS.md, bootstrap.sh updated, CLAUDE.md and README.md updated. Ready for archive. |
| 2026-02-05 | Cross-referenced with gemini-mirror plan. All phases complete. |
