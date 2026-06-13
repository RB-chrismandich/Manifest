---
name: health-check
description: |
  Verify CLI tool availability, authentication status, config syntax,
  MCP connectivity, and symlink integrity for the Manifest environment.
---

# Health Check Skill

Run a comprehensive diagnostic of the Manifest agent environment to detect
misconfiguration, missing tools, broken symlinks, or authentication issues.

> **Scope note:** This skill covers config syntax, MCP connectivity, symlinks,
> labels, and script executability. For a quick terminal check of parallel
> orchestration readiness (enabled agents, state directories), run:
> `~/.claude/scripts/check_status.sh` (also available as `parallel_agent.py --status`).

## Checks

Execute each check category below. Collect results into a summary table.

### 1. CLI Tool Availability

For each service in `.claude/config/services.yml` where `enabled: true`:

```bash
command -v <tool_command> &>/dev/null
<tool_command> --version 2>/dev/null || <tool_command> version 2>/dev/null
```

Report: installed (with version) or missing.

### 2. Authentication Status

Check authentication for each enabled service:

- **Claude**: `claude auth status 2>/dev/null` or check `ANTHROPIC_API_KEY` is set
- **Gemini**: `gemini auth status 2>/dev/null` or check `GOOGLE_API_KEY` is set
- **Cursor**: `cursor --version` (no separate auth check; presence implies configured)
- **GitHub CLI**: `gh auth status 2>/dev/null`
- **GitLab CLI**: `glab auth status 2>/dev/null`

Report: authenticated, unauthenticated, or not applicable.

### 3. Configuration Syntax

Validate YAML and JSON config files:

```bash
python3 -c "import yaml; yaml.safe_load(open('<file>'))" 2>&1
python3 -c "import json; json.load(open('<file>'))" 2>&1
```

Files to check:

- `.claude/config/command_config.yml`
- `.claude/config/parallel_agent.yml`
- `.claude/config/services.yml`
- `.claude/config/validation_criteria.yml`
- `.claude/config/linear_triage.yml`
- `.claude/config/mcp_servers.yml`
- `.claude/config/labels.yml`
- `.claude/settings.local.json`

Report: valid or error details.

### 4. MCP Server Connectivity

For each server in `.claude/config/mcp_servers.yml`:

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 5 <url>
```

Report: reachable (HTTP status) or unreachable.

### 5. Symlink Integrity

Verify all cross-platform symlinks are intact:

```bash
# Expected symlinks (target → source)
.cursor/scripts  → ../.claude/scripts
.cursor/config   → ../.claude/config
.cursor/prompts  → ../.claude/prompts
.cursor/skills   → ../.claude/skills
.cursor/.plans   → ../.claude/.plans
.gemini/scripts  → ../.claude/scripts
.gemini/config   → ../.claude/config
.gemini/prompts  → ../.claude/prompts
.gemini/skills   → ../.claude/skills
.gemini/.plans   → ../.claude/.plans
.codex/scripts   → ../.claude/scripts
.codex/config    → ../.claude/config
.codex/prompts   → ../.claude/prompts
.codex/skills    → ../.claude/skills
.codex/.plans    → ../.claude/.plans
.antigravity/scripts → ../.claude/scripts
.antigravity/config  → ../.claude/config
.antigravity/prompts → ../.claude/prompts
.antigravity/skills  → ../.claude/skills
.antigravity/.plans  → ../.claude/.plans
```

Only check symlinks for services marked `enabled: true` in
`.claude/config/services.yml` (e.g. skip `.cursor`/`.codex` when disabled).

For each: check if symlink exists and target is valid.

Report: intact, broken (dangling), or missing.

### 6. Label Registry Validation

Verify the label registry is valid and labels are consistent:

1. Check `.claude/config/labels.yml` exists and is valid YAML
2. Verify each label has required fields: `name`, `color`, `description`, `platforms`
3. Verify color values are valid 6-digit hex (no leading `#`)
4. Check for duplicate label names
5. If `gh` is available, run `gh label list --json name,color` and compare against registry

```bash
# Validate labels.yml syntax
python3 -c "
import yaml, sys
with open('.claude/config/labels.yml') as f:
    data = yaml.safe_load(f)
labels = data.get('labels', [])
for label in labels:
    assert 'name' in label, f'Missing name in label: {label}'
    assert 'color' in label, f'Missing color in {label[\"name\"]}'
    assert 'platforms' in label, f'Missing platforms in {label[\"name\"]}'
    assert len(label['color']) == 6, f'Invalid color hex in {label[\"name\"]}: {label[\"color\"]}'
print(f'{len(labels)} labels validated')
"
```

Report: valid (N labels) or error details.

### 7. Browser-Use Availability (Info)

Check if browser-use is available for E2E testing:

```bash
# Check CLI
command -v browser-use &>/dev/null && browser-use --version 2>/dev/null

# Check Python module
python3 -c "import browser_use; print(browser_use.__version__)" 2>/dev/null
```

Report: installed (with version) or not installed.

This check is **informational only** — browser-use is an optional tool.
Report as `info` (not `fail`) when missing.

### 8. Script Executability

Verify all scripts in `.claude/scripts/` are executable:

```bash
[[ -x "$script" ]]
```

Report: executable or not executable.

## SkillClaw (if enabled)

Only when `skillclaw.enabled: true` in `~/.claude/config/services.yml`:

SkillClaw is proxy-free (`bootstrap/lib/skillclaw.sh`): no daemon, no socket,
no shell wrappers. Enabling means storage-only setup.

```bash
# Storage exists and is locked down (must be 700) — GNU-first for Linux/macOS
stat -c '%a' ~/.skillclaw 2>/dev/null || stat -f '%Lp' ~/.skillclaw

# Legacy artifacts must be ABSENT (leftovers from the pre-proxy-free install)
grep -q "MANIFEST SKILLCLAW WRAPPERS" "${ZDOTDIR:-$HOME}/.zshrc" && echo "legacy wrappers: PRESENT (stale)" || echo "legacy wrappers: absent (ok)"
ls ~/Library/LaunchAgents/*skillclaw* 2>/dev/null && echo "legacy plist: PRESENT (stale)" || echo "legacy plist: absent (ok)"
```

Report storage perms != 700 as WARN; legacy wrappers or plist PRESENT as WARN
(rerun `./bootstrap.sh` to clean them). Storage missing entirely as WARN
(enable was never completed).

## Output Format

```text
## Health Check Report

| Category | Check | Status | Details |
|----------|-------|--------|---------|
| CLI Tools | claude | pass | v4.x.x |
| CLI Tools | gemini | pass | v1.x.x |
| CLI Tools | cursor | fail | Not installed |
| Auth | claude | pass | Authenticated |
| Auth | gh | warn | Not configured |
| Config | command_config.yml | pass | Valid YAML |
| Config | services.yml | fail | Parse error on line 12 |
| MCP | sentry | pass | HTTP 200 |
| MCP | linear | warn | HTTP 401 (auth required) |
| Symlinks | .cursor/scripts | pass | Intact |
| Symlinks | .gemini/config | fail | Broken |
| Labels | labels.yml | pass | 5 labels validated |
| Scripts | parallel_agent.py | pass | Executable |

### Summary

- pass: N checks passed
- warn: N warnings (non-blocking)
- fail: N failures (action needed)
```

## Tool Usage

- **Bash**: Run CLI version checks, auth status, curl, stat, test
- **Read**: Read config files for validation
- **Glob**: Find config and script files
- **Grep**: Search for configuration values
