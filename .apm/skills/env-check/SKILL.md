---
name: env-check
description: Verify CLI tool availability, authentication status, config syntax, MCP connectivity, and symlink integrity for the Manifest environment.
---

# Health Check Skill

Run a comprehensive diagnostic of the Manifest agent environment to detect
misconfiguration, missing tools, broken symlinks, or authentication issues.

> **Scope note:** This skill covers config syntax, MCP connectivity, symlinks,
> labels, and script executability. For a quick terminal check of parallel
> orchestration readiness (enabled agents, state directories), run:
> `~/.claude/scripts/check_status.sh` (also available as `manifest parallel-agent --status`).

## Checks

Execute each check category below. Collect results into a summary table.

### Deploy Ownership (feature 522)

Report which pipeline owns each deployed domain, and flag any domain claimed by
**both** (the drift condition) or by **neither** (it silently stops updating):

```bash
~/.claude/scripts/apm_ownership_report.sh          # human-readable
~/.claude/scripts/apm_ownership_report.sh --json   # machine-readable
```

Read-only. Exit 1 means a domain is double-claimed or unowned — report the
`DOUBLE-CLAIMED` / `UNOWNED` line verbatim, and note that `UNOWNED` is expected
only during a hand-over window (`apm_ungate_domain.sh <domain> --apply` returns
it to the legacy pipeline).

### 1. CLI Tool Availability

For each service in `~/.claude/config/services.yml` where `enabled: true`:

```bash
command -v <tool_command> &>/dev/null
<tool_command> --version 2>/dev/null || <tool_command> version 2>/dev/null
```

Report: installed (with version) or missing.

This loop also covers **graphify** (`command: graphify`) — the knowledge-graph
tool. It is a managed tool, not a parallel-orchestration agent, so it does not
count toward orchestration readiness; report it as installed or missing only.

### 2. Home Python Runtime

Manifest's Python tools run from a uv-managed venv at `~/.claude/.venv` (not
system `python3` or retired `pip install --user`). Treat any hard failure here
as **BLOCKED** (same severity as a missing `~/.claude/skills` symlink).

```bash
MANIFEST_PY="${HOME}/.claude/.venv/bin/python"

command -v uv &>/dev/null && uv --version 2>/dev/null
[[ -x "$MANIFEST_PY" ]] && "$MANIFEST_PY" --version 2>/dev/null
command -v manifest &>/dev/null && manifest --help &>/dev/null
manifest doctor
```

Report per check:

| Check | pass | fail (BLOCKED) |
|-------|------|----------------|
| `uv` on PATH | version shown | missing |
| `~/.claude/.venv` | `$MANIFEST_PY` exists and runs | absent or not executable |
| `manifest` on PATH | help exits 0 | missing or broken wrapper |
| `manifest doctor` | exit 0 (core imports: `anthropic`, `yaml`, etc.) | exit non-zero |

When `smoke.enabled: true` in `~/.claude/config/services.yml`, `manifest doctor`
must also import `playwright` — treat failure as **BLOCKED**. When
`browser_use.enabled: true`, `doctor` must import `browser_use` — also
**BLOCKED**. Missing optional deps when the corresponding service is disabled
are **warn** only.

### 3. Authentication Status

The fleet's per-agent auth check is not a hand-maintained list — read it from
`~/.claude/config/agent_roster.yml` (`agents.<name>.auth_check`) and run each
entry:

```bash
python3 -c "
import yaml
roster = yaml.safe_load(open('$HOME/.claude/config/agent_roster.yml'))['agents']
for name, agent in roster.items():
    print(f'{name}: {agent[\"auth_check\"]}')
"
```

Run each printed `auth_check` command and report authenticated/unauthenticated
per agent, applying these per-agent quirks:

- **claude**: `claude auth status` — if unavailable, checking `ANTHROPIC_API_KEY`
  is set is an equally valid pass.
- **gemini**: `gemini auth status` — if unavailable, checking `GOOGLE_API_KEY`
  is set is an equally valid pass.
- **cursor**: `cursor-agent --version` only confirms the binary runs, not that
  it's authenticated — no stronger non-interactive check is documented yet
  (see `agent_roster.yml`'s provenance notes on `cursor-agent status|whoami`
  as a future candidate). Report accordingly, don't treat it as a strong pass.
- **codex**: `codex login status` is the CLI-native check. If it requires
  interactivity in this environment, fall back to the non-interactive check
  `bootstrap/lib/auth.sh`'s `check_codex_auth` actually uses: `OPENAI_API_KEY`
  set, or `~/.codex/auth.json` / `~/.config/codex/auth.json` present.
- **antigravity**: `agy models` is a deliberate live probe, not a version
  check — `agy` has no persisted auth-file to inspect, so this command only
  succeeds when logged in (see `bootstrap/lib/auth.sh`'s `check_antigravity_auth`).

Also check these non-fleet services, which are not in `agent_roster.yml`:

- **GitHub CLI**: `gh auth status 2>/dev/null`
- **GitLab CLI**: `glab auth status 2>/dev/null`
- **Graphify**: not applicable — default host-agent backend uses the running assistant as the LLM (no key)

Report: authenticated, unauthenticated, or not applicable.

### 4. Configuration Syntax

Validate YAML and JSON config files (use the home venv — not system `python3`):

```bash
MANIFEST_PY="${HOME}/.claude/.venv/bin/python"
"$MANIFEST_PY" -c "import yaml; yaml.safe_load(open('<file>'))" 2>&1
"$MANIFEST_PY" -c "import json; json.load(open('<file>'))" 2>&1
```

Files to check:

- `~/.claude/config/command_config.yml`
- `~/.claude/config/parallel_agent.yml`
- `~/.claude/config/services.yml`
- `~/.claude/config/validation_criteria.yml`
- `~/.claude/config/tracker_triage.yml`
- `~/.claude/config/mcp_servers.yml`
- `~/.claude/config/labels.yml`
- `.claude/settings.local.json`

Report: valid or error details.

### 5. MCP Server Connectivity

For each server in `~/.claude/config/mcp_servers.yml`:

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 5 <url>
```

Report: reachable (HTTP status) or unreachable.

### 6. Symlink Integrity

Verify all cross-platform symlinks are intact. The mirror set is not a fixed
4/5-tuple — it's every agent in `~/.claude/config/agent_roster.yml` except
`claude` itself (the physical config home the others link back to):

```bash
python3 -c "
import yaml
roster = yaml.safe_load(open('$HOME/.claude/config/agent_roster.yml'))['agents']
for name, agent in roster.items():
    if name == 'claude':
        continue
    print(f'{name}: {agent[\"home_dir\"]}')
"
```

For each mirror `home_dir` from the roster (`.cursor`, `.gemini`, `.codex`,
`.antigravity` today — automatically picks up a 6th agent if the roster
gains one), the standard link set is:

```text
<home>/scripts  → ../.claude/scripts
<home>/config   → ../.claude/config
<home>/prompts  → ../.claude/prompts
<home>/skills   → ../.claude/skills
<home>/.plans   → ../.claude/.plans
```

**Quirk — antigravity is a partial mirror:** `.antigravity` only gets
`config`, `skills`, `.plans` — no `scripts` or `prompts` symlink, because
`agy` is a `parallel_agent.py` CLI provider, not an orchestrator that reads
scripts/prompts directly. Don't report its missing `scripts`/`prompts`
symlinks as broken or missing.

Only check symlinks for services marked `enabled: true` in
`~/.claude/config/services.yml` (e.g. skip `.cursor`/`.codex` when disabled).

For each: check if symlink exists and target is valid.

Report: intact, broken (dangling), or missing.

### 7. Label Registry Validation

Verify the label registry is valid and labels are consistent:

1. Check `~/.claude/config/labels.yml` exists and is valid YAML
2. Verify each label has required fields: `name`, `color`, `description`, `platforms`
3. Verify color values are valid 6-digit hex (no leading `#`)
4. Check for duplicate label names
5. If `gh` is available, run `gh label list --json name,color` and compare against registry

```bash
# Validate labels.yml syntax (home venv)
MANIFEST_PY="${HOME}/.claude/.venv/bin/python"
"$MANIFEST_PY" -c "
import yaml, sys
with open('~/.claude/config/labels.yml') as f:
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

### 8. Browser-Use Availability (Info)

Check if browser-use is available for E2E testing:

```bash
# Check CLI
command -v browser-use &>/dev/null && browser-use --version 2>/dev/null

# Check Python module (home venv when browser-use group is installed)
MANIFEST_PY="${HOME}/.claude/.venv/bin/python"
"$MANIFEST_PY" -c "import browser_use; print(browser_use.__version__)" 2>/dev/null
```

Report: installed (with version) or not installed.

This check is **informational only** — browser-use is an optional tool.
Report as `info` (not `fail`) when missing.

### 9. Script Executability

Verify all scripts in `~/.claude/scripts/` are executable:

```bash
[[ -x "$script" ]]
```

Report: executable or not executable.

### 10. emdash Inheritance (Info)

[emdash](https://github.com/generalaction/emdash) is an external **harness** (not
a Manifest deploy target) that launches your agent CLIs in parallel git worktrees
using your **real `HOME`** — so a Manifest-configured agent inherits the full
config transitively. This check reports whether that inheritance path is intact
and surfaces the one coexistence caveat (FR-010, SC-005). Uses the shared probe
`configs/claude/scripts/emdash_inherit_check.sh` (deployed to `~/.claude/scripts/`).

Detect emdash first (optional harness — report `info`, not `fail`, when absent):

```bash
# macOS app bundle or the emdash worktrees directory
[[ -d /Applications/Emdash.app || -d "$HOME/emdash" ]] \
    && echo "emdash: detected" || echo "emdash: not detected (optional)"
```

When emdash is detected, run the shared inheritance probe live and render its
per-dimension report:

```bash
~/.claude/scripts/emdash_inherit_check.sh          # human report
~/.claude/scripts/emdash_inherit_check.sh --json   # machine-readable (same result)
```

Render one row per dimension — D1 skills, D2 subagents, D3 hooks, D4 MCP,
D5 orchestration guide, D6 repo guides — plus the overall verdict:

- **`INHERITED`** (exit 0) — all dimensions resolve → report `pass`.
- **`DEGRADED`** (exit 1) — ≥1 dimension `FAIL` → report `warn` with the failing dimension(s).
- **`BLOCKED`** (exit 2) — **prerequisite not met**: the Manifest home deployment
  has not been run (`~/.claude` absent), so emdash sessions inherit only the
  repo's committed config. Report `warn` with the fix: run `./bootstrap.sh`, then re-check.

**Hook-coexistence caveat**: emdash appends its own `Stop` hook
(`curl http://127.0.0.1:$EMDASH_HOOK_PORT/hook`, marker-tagged) to the agent's
settings file on each spawn and adds that path to `.gitignore`. Manifest's hooks
(home `~/.claude/settings.local.json`) and the repo's committed permissions are expected
to be preserved by emdash's idempotent merge. In a live run the probe has no
independent pre-merge snapshot to diff against, so `coexistence.manifest_hooks_preserved`
and `worktree_permissions_intact` report `null` (`unverified`) rather than a
false `true` — treat this as informational, not a live guarantee. The
deterministic version of this check (a real pre/post diff) runs in
`tests/bats/emdash_inheritance.bats` against a fixture, where those flags are
genuine `true`/`false`. The injected machine-local hook is expected to stay
**uncommitted**; do not commit it. See `docs/EMDASH.md`.

Report: `pass` (INHERITED), `warn` (BLOCKED home-deploy-missing, or DEGRADED),
or `info` (emdash not detected — optional harness).

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
pgrep -f skillclaw >/dev/null 2>&1 && echo "legacy daemon process: RUNNING (stale)" || echo "legacy daemon process: absent (ok)"
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
| Runtime | uv | pass | v0.x.x |
| Runtime | manifest doctor | pass | Core imports OK |
| Runtime | manifest | pass | On PATH |

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
