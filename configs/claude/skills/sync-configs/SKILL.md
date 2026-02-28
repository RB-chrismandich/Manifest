---
name: sync-configs
description: |
  Verify cross-platform configuration consistency, check symlink integrity,
  and detect config drift between Claude, Cursor, Gemini, and Codex platforms.
---

# Sync Configs Skill

Audit the Manifest deployment for configuration drift across platforms.
Detects broken symlinks, missing files, and divergence between the canonical
`.claude/` source and platform-specific directories.

## Checks

Execute each check category below. Collect results into a summary table.

### 1. Symlink Integrity

Verify all expected symlinks exist and point to valid targets.

**Expected symlinks** (from repo root):

| Platform | Symlink           | Target               |
| -------- | ----------------- | -------------------- |
| Cursor   | `.cursor/scripts` | `../.claude/scripts` |
| Cursor   | `.cursor/config`  | `../.claude/config`  |
| Cursor   | `.cursor/prompts` | `../.claude/prompts` |
| Cursor   | `.cursor/skills`  | `../.claude/skills`  |
| Cursor   | `.cursor/.plans`  | `../.claude/.plans`  |
| Gemini   | `.gemini/scripts` | `../.claude/scripts` |
| Gemini   | `.gemini/config`  | `../.claude/config`  |
| Gemini   | `.gemini/prompts` | `../.claude/prompts` |
| Gemini   | `.gemini/skills`  | `../.claude/skills`  |
| Gemini   | `.gemini/.plans`  | `../.claude/.plans`  |
| Codex    | `.codex/scripts`  | `../.claude/scripts` |
| Codex    | `.codex/config`   | `../.claude/config`  |
| Codex    | `.codex/prompts`  | `../.claude/prompts` |
| Codex    | `.codex/skills`   | `../.claude/skills`  |
| Codex    | `.codex/.plans`   | `../.claude/.plans`  |

For each symlink:

```bash
if [[ -L "$symlink" ]]; then
    target=$(readlink "$symlink")
    if [[ -e "$symlink" ]]; then
        echo "intact"
    else
        echo "broken (dangling → $target)"
    fi
else
    echo "missing (not a symlink)"
fi
```

### 2. Cursor Rules Drift

Check if `.cursor/rules/*.mdc` files are up-to-date with SKILL.md sources.

```bash
# Run in dry-run mode
.claude/scripts/generate_cursor_rules.sh --dry-run
```

If any would be updated, report the drift.

### 3. Gemini Command Parity

Verify that each `.claude/commands/*.md` has a corresponding `.gemini/commands/*.toml`.

```bash
for cmd in .claude/commands/*.md; do
    name=$(basename "$cmd" .md)
    toml=".gemini/commands/${name}.toml"
    if [[ ! -f "$toml" ]]; then
        echo "missing: $toml"
    fi
done
```

### 4. MCP Configuration Consistency

Compare MCP server configurations across platforms:

- `.claude/settings.local.json` → `.mcpServers`
- `.cursor/mcp.json`
- `.gemini/settings.json` → `mcpServers`

For each platform, extract server names and URLs. Flag any differences from
the canonical `.claude/config/mcp_servers.yml`.

### 5. Config File Freshness

For shared config files accessed via symlink, verify that the canonical files
in `.claude/config/` have not been bypassed by platform-specific copies.

```bash
# These should NOT exist as regular files if symlinks are working
for platform in .cursor .gemini .codex; do
    for cfg in config/command_config.yml config/services.yml; do
        path="$platform/$cfg"
        if [[ -f "$path" && ! -L "$platform/config" ]]; then
            echo "drift: $path is a regular file (should be via symlink)"
        fi
    done
done
```

## Output Format

```text
## Sync Configs Report

| Category | Platform | Item | Status | Details |
|----------|----------|------|--------|---------|
| Symlinks | Cursor | scripts | pass | Intact → ../.claude/scripts |
| Symlinks | Gemini | config | fail | Missing |
| Rules | Cursor | issue-triage.mdc | warn | Outdated (would update) |
| Commands | Gemini | health-check.toml | fail | Missing |
| MCP | Cursor | sentry | pass | Matches canonical |
| MCP | Gemini | linear | warn | URL differs from canonical |

### Summary

- pass: N checks passed
- warn: N warnings (drift detected but functional)
- fail: N failures (broken or missing)
```

## Tool Usage

- **Bash**: Run readlink, stat, diff, generate_cursor_rules.sh --dry-run
- **Read**: Read config files for comparison
- **Glob**: Find config and command files across platforms
- **Grep**: Search for configuration values
