# Antigravity Support Design

**Date**: 2026-06-01
**Status**: Approved
**Scope**: Add Antigravity IDE as a first-class platform target in the Manifest bootstrap system

---

## Overview

Antigravity is a VS Code-fork IDE with the Claude Code extension installed. Because the
extension reads `~/.claude/` natively, Antigravity already inherits skills, settings,
permissions, and MCP config without any extra configuration. This spec adds the remaining
structural pieces to make Antigravity a fully-recognized platform target alongside
Cursor, Gemini, and Codex.

---

## Design Decisions

### Inherit from `~/.claude/` — no separate config

Antigravity's Claude Code extension reads `~/.claude/` directly. There is no need to
deploy a separate `settings.json`, `ANTIGRAVITY.md`, or MCP config. All permissions and
MCP servers inherited from `~/.claude/settings.local.json` automatically.

Rationale: a separate config file would be a "zombie" — no reader, guaranteed drift.

### `configs/antigravity/` is a symlink hub only

The directory contains 5 symlinks pointing at `../claude/`. No standalone files.
This mirrors the Codex pattern and keeps the repo a reflection of deployment state
rather than a storage locker for redundant metadata.

### `~/.antigravity/skills` stays a symlink

`deploy_antigravity_configs` already creates `~/.antigravity/skills → ~/.claude/skills`.
`sync-skills.sh` does not need to add Antigravity as a target — the symlink
auto-propagates any update to `~/.claude/skills` instantly.

### `deploy_antigravity_configs` remains unconditional

Config deployment is unconditional for all secondary targets (cursor, gemini, codex,
antigravity). The `ENABLE_ANTIGRAVITY` toggle gates install summary reporting only,
consistent with the established pattern.

---

## Components

### 1. `configs/antigravity/` — repo directory

New directory with 5 symlinks:

```
configs/antigravity/
├── scripts   -> ../claude/scripts
├── config    -> ../claude/config
├── prompts   -> ../claude/prompts
├── skills    -> ../claude/skills
└── .plans    -> ../claude/.plans
```

No additional files. No `ANTIGRAVITY.md`.

### 2. Bootstrap toggle — `ENABLE_ANTIGRAVITY`

Four touch points in `bootstrap.sh` and `bootstrap/lib/deploy.sh`:

| Location | Change |
|----------|--------|
| `bootstrap.sh` usage block | Add `--enable-antigravity` / `--disable-antigravity` comment |
| `bootstrap.sh` arg parsing | Parse `--enable-antigravity` / `--disable-antigravity` flags; default `true` |
| `write_services_config` | Emit `antigravity: true/false` in `services.yml` |
| Reconfigure display | Show `Antigravity: $old → $ENABLE_ANTIGRAVITY` |
| Install summary | Check `/Applications/Antigravity.app`; print success/warning/disabled |

Default: `ENABLE_ANTIGRAVITY=true` — consistent with all other targets.

`deploy_antigravity_configs` call site is **not** gated by the toggle.

### 3. Bats test suite

**`tests/bats/deploy_skills.bats`** — existing file; add alongside the current test:

| # | Test | Validates |
|---|------|-----------|
| 1 | (existing) symlinks `~/.antigravity/skills` to `~/.claude/skills` | Basic deploy |
| 2 | Idempotency — run `deploy_antigravity_configs` twice, assert no error and symlink intact | Repeated deploys safe |
| 3 | Skills symlink target is resolvable — `readlink -f` resolves to an existing directory | No dangling links |

**`tests/bats/deploy_antigravity.bats`** — new file for structural/repo tests:

| # | Test | Validates |
|---|------|-----------|
| 4 | `configs/antigravity/` symlinks each resolve to `../claude/` equivalents | Repo structure integrity |

**`tests/bats/bootstrap_services.bats`** (new file or added to existing):

| # | Test | Validates |
|---|------|-----------|
| 5 | `write_services_config` with `ENABLE_ANTIGRAVITY=false` emits `antigravity: false` in `services.yml` | Toggle persisted to config |

Test 3 note: assert `[ -e "$link_target" ]` before path equality check for a clean error
message when the target is missing vs. wrong.

### 4. Documentation updates

- `CLAUDE.md` repository structure table: add `configs/antigravity/` row
- `README.md` supported platforms section: add Antigravity
- `docs/COMMANDS.md` or equivalent: add `--enable/--disable-antigravity` to flag table

---

## What Does Not Change

| Item | Reason |
|------|--------|
| `deploy_antigravity_configs()` body | Already correct |
| `~/.antigravity/skills` symlink target | Already live |
| `sync-skills.sh` | No changes — symlink auto-inherits |
| `~/.claude/settings.local.json` | Antigravity inherits it natively |
| MCP configuration | Inherited from `~/.claude/` via extension |

---

## Acceptance Criteria

- [ ] `configs/antigravity/` exists with 5 correct symlinks
- [ ] `./bootstrap.sh --disable-antigravity` writes `antigravity: false` to `services.yml`
- [ ] `./bootstrap.sh` summary prints Antigravity availability status
- [ ] `./bootstrap.sh --reconfigure --disable-antigravity` shows old → new transition
- [ ] All 5 bats tests pass
- [ ] `shellcheck` clean on modified bootstrap files
- [ ] Docs updated (CLAUDE.md layout table, README platforms, flag reference)
