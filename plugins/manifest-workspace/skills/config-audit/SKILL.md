---
name: config-audit
description: Verify cross-platform config drift and symlink integrity across Claude, Cursor, Gemini, Codex, and Antigravity.
---

# Sync Configs Skill

Audit the Manifest deployment for configuration drift across platforms.
Detects broken symlinks, missing files, and divergence between the canonical
`.claude/` source and platform-specific directories.

## Checks

Execute each check category below. Collect results into a summary table.

### 1. Symlink Integrity

Verify all expected symlinks exist and point to valid targets. The platform
set is not a fixed 3/4-tuple — it's every agent in
`~/.claude/config/agent_roster.yml` except `claude` itself (the physical
config home the others link back to):

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

**Expected symlinks** (from repo root, per mirror `home_dir` — `.cursor`,
`.gemini`, `.codex`, `.antigravity` today):

| Symlink | Target |
|---------|--------|
| `<home>/scripts` | `../.claude/scripts` |
| `<home>/config` | `../.claude/config` |
| `<home>/prompts` | `../.claude/prompts` |
| `<home>/skills` | `../.claude/skills` |
| `<home>/.plans` | `../.claude/.plans` |

**Quirk — antigravity is a partial mirror:** `.antigravity` only gets
`config`, `skills`, `.plans` (no `scripts`/`prompts` — `agy` is a
`parallel_agent.py` CLI provider, not an orchestrator that reads
scripts/prompts directly). Don't report its missing `scripts`/`prompts`
symlinks as drift.

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
~/.claude/scripts/generate_cursor_rules.sh --dry-run
```

If any would be updated, report the drift.

### 3. Gemini Command Parity

Verify that each `~/.claude/commands/*.md` has a corresponding `.gemini/commands/*.toml`.

```bash
for cmd in ~/.claude/commands/*.md; do
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

The canonical registry is `~/.claude/config/mcp_servers.yml` (`mcp_servers:`
mapping). For each platform, extract deployed server names and URLs and
compare against the **full canonical list**, not just the servers already
present — a server the registry defines but a platform never picked up is
drift too, and is easy to miss if the check only walks the deployed subset:

Detect missing servers by **exact top-level key membership** in the deployed
`mcpServers` object — never a substring `grep`, since a registry name that is a
substring of another quoted token (or of a URL) would false-negative:

```bash
python3 -c "
import yaml, json
registry = yaml.safe_load(open('$HOME/.claude/config/mcp_servers.yml')).get('mcp_servers', {})
canonical = sorted(registry)
deployed = json.load(open('$HOME/.cursor/mcp.json')).get('mcpServers', {})
for name in canonical:
    if name not in deployed:          # exact key membership, not substring
        print(f'missing: {name} not in .cursor/mcp.json')
"
```

Flag BOTH kinds of drift, per platform:

- **present but mismatched** — a deployed server's URL/command differs from canonical.
- **missing** — a canonical registry server absent from a platform's deployed
  config entirely. Report each missing server by name so it's actionable
  (e.g. regenerate via `generate_cursor_mcp.py` for Cursor, or update the
  hand-maintained `settings.local.json`/`settings.json` block for
  Claude/Gemini).

**Quirk — codex and antigravity are out of scope for this file-diff check:**
this check only covers the three platforms above; it does not check codex or
antigravity, and not because they were forgotten. Per `bootstrap/lib/mcp.sh`:

- **codex** is CLI-managed, not file-managed — `install_codex_mcp_server()`
  registers servers via `codex mcp add <name> --url <url>` (and removes/lists
  via `codex mcp remove`/`codex mcp list`); there is no static
  `~/.codex/mcp.json`-equivalent file to diff against the canonical registry.
  Auditing codex would mean shelling out to `codex mcp list` and parsing its
  tabular output — a different check mechanism, out of scope here.
- **antigravity** has no scriptable MCP CLI at all — `bootstrap/lib/mcp.sh`
  documents (verified live on agy 1.1.1, G16/agy-batchD-groundtruth.md) that
  `agy --help` lists no `mcp` subcommand and `agy mcp --help` falls through to
  the general usage banner. Its config also lives under `~/.gemini/config`
  (Gemini-CLI lineage), not a dedicated `~/.antigravity` MCP file, so whatever
  MCP state it has is already covered (or not) by the Gemini check above.

Don't report codex/antigravity as missing from this check — that's by design,
not drift. If a future audit wants codex coverage, it needs a
`codex mcp list`-parsing check, not an extension of this file-diff approach.

### 5. Config File Freshness

For shared config files accessed via symlink, verify that the canonical files
in `~/.claude/config/` have not been bypassed by platform-specific copies.

```bash
# Platforms come from agent_roster.yml's home_dir values (every agent except
# claude, the canonical source) — not a hardcoded list. These should NOT
# exist as regular files if symlinks are working.
platforms=$(python3 -c "
import yaml
roster = yaml.safe_load(open('$HOME/.claude/config/agent_roster.yml'))['agents']
print(' '.join(a['home_dir'].replace('~/.', '.') for n, a in roster.items() if n != 'claude'))
")

for platform in $platforms; do
    for cfg in config/command_config.yml config/services.yml; do
        path="$platform/$cfg"
        if [[ -f "$path" && ! -L "$platform/config" ]]; then
            echo "drift: $path is a regular file (should be via symlink)"
        fi
    done
done
```

### 6. SkillClaw Config Drift (if enabled)

Only when `skillclaw.enabled: true` in `~/.claude/config/services.yml`.

- `config/skillclaw.yml` — SkillClaw runtime config (port, storage, evolve provider,
  promotion settings). Compare `configs/claude/config/skillclaw.yml` (source) against
  the deployed `~/.claude/config/skillclaw.yml`; flag drift in port or storage root.

```bash
diff configs/claude/config/skillclaw.yml ~/.claude/config/skillclaw.yml 2>/dev/null \
    && echo "skillclaw.yml: in sync" \
    || echo "skillclaw.yml: DRIFT DETECTED"
```

Pay particular attention to `port` and `storage_root` fields — divergence there
can cause the daemon and wrappers to disagree on where data lives.

### 7. emdash Hook Coexistence (awareness — not drift)

The [emdash](https://github.com/generalaction/emdash) harness launches agent CLIs
in git worktrees using the real `HOME`. On each spawn it **appends its own `Stop`
hook** (`curl http://127.0.0.1:$EMDASH_HOOK_PORT/hook`, marker-tagged for idempotent
dedup) to the agent's `.claude/settings.local.json` and adds that path to `.gitignore`.
This is expected and does **not** indicate config drift:

- Manifest's event **hooks** (and `mcpServers`) are deployed into home
  `~/.claude/settings.local.json`; the repo's tracked worktree
  `.claude/settings.local.json` holds **permissions** only. emdash's append
  coexists with both — its idempotent merge preserves existing entries.
- If an audit surfaces an emdash `Stop` hook or a new `.gitignore` line for a
  settings file, treat it as machine-local **coexistence, not a drift finding**.
  The injected hook is expected to stay **uncommitted** — do not commit it.

See `docs/EMDASH.md` for the full coexistence caveat.

### Deploy Ownership (feature 522)

Report which pipeline owns each deployed domain, and flag any domain claimed by
**both** (the drift condition) or by **neither** (it silently stops updating):

```bash
~/.claude/scripts/apm_ownership_report.sh          # human-readable
~/.claude/scripts/apm_ownership_report.sh --json   # machine-readable
```

Read-only. Exit 1 means a domain is double-claimed or unowned — report the
`DOUBLE-CLAIMED` / `UNOWNED` / `PARTIAL` line verbatim, and note that `UNOWNED`
is expected only during a hand-over window (`apm_ungate_domain.sh <domain>
--apply` returns it to the legacy pipeline).

`plugins` and `harness-skills` appear only when there is something to report, so
**absence is not a failure**. `plugins` `DOUBLE-CLAIMED` = a skill served by both
a bundle and `~/.claude/skills` (both load, neither wins, both charged to the
listing budget). `harness-skills` `PARTIAL` = a sibling home pointing away from
the harness tree; `./bootstrap.sh` repoints it.

## Output Format

```text
## Sync Configs Report

| Category | Platform | Item | Status | Details |
|----------|----------|------|--------|---------|
| Symlinks | Cursor | scripts | pass | Intact → ../.claude/scripts |
| Symlinks | Gemini | config | fail | Missing |
| Rules | Cursor | issue-triage.mdc | warn | Outdated (would update) |
| Commands | Gemini | env-check.toml | fail | Missing |
| MCP | Cursor | sentry | pass | Matches canonical |
| MCP | Gemini | linear | warn | URL differs from canonical |
| MCP | Cursor | deepwiki | fail | Missing — in registry, not in .cursor/mcp.json |

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
