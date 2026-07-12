# Contract: `emdash_inherit_check.sh` Inheritance Probe

**Interface**: a Manifest CLI script that reports whether a Manifest-configured agent, launched by emdash in a given worktree with a given `HOME`, inherits the full Manifest configuration. It is the single source of truth shared by `/env-check` (live) and `tests/bats/emdash_inheritance.bats` (fixture) — FR-010, FR-011a, R6.

## Invocation

```text
emdash_inherit_check.sh [--home <dir>] [--worktree <dir>] [--json] [--help]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--home <dir>` | `$HOME` | Home dir whose `.claude/` is the deployed Manifest config |
| `--worktree <dir>` | `$PWD` | Worktree checkout to inspect for committed repo config |
| `--json` | off | Emit machine-readable report (for the test); default is human report (for env-check) |
| `--help` | — | Usage ≤15 lines, exit 0 (repo convention) |

Conventions (repo standards): errors via `err() { echo "emdash_inherit_check.sh: $*" >&2; }`; `--help` succeeds before any config lookup; fails closed.

## Dimensions checked (from data-model E2)

| ID | Check | PASS when |
|----|-------|-----------|
| D1 Skills | count `~/.claude/skills/*/SKILL.md` | ≥ 1 |
| D2 Subagents | presence of `~/.claude/agents/*.md` and/or `<worktree>/.claude/agents/*.md` | Manifest subagents reachable |
| D3 Hooks | Manifest hooks in HOME `~/.claude/settings.json`; re-check after simulated emdash merge (home-scope) + worktree permissions after worktree-scope merge | Manifest hooks present AND survive the append; worktree permissions not corrupted |
| D4 MCP | `mcpServers` in `~/.claude/settings.json` / `.mcp.json` | ≥ 1 Manifest MCP server resolvable |
| D5 Orchestration guide | `<home>/.claude/CLAUDE.md`, `<worktree>/CLAUDE.md`, `<worktree>/.claude/CLAUDE.md` | guide files readable |
| D6 Repo guides | `<worktree>/AGENTS.md`, `<worktree>/.claude/` | committed guidance present |

## Output

**Human (`/env-check`)** — one line per dimension with `PASS`/`FAIL`/`INFO` + detail, then an overall verdict line and the coexistence note.

**JSON (`--json`, for the test)**:
```json
{
  "verdict": "INHERITED",              // INHERITED | DEGRADED | BLOCKED
  "dimensions": {
    "skills":  {"status":"PASS","detail":"88 reachable"},
    "subagents":{"status":"PASS","detail":"6 reachable"},
    "hooks":   {"status":"PASS","detail":"manifest hooks present; preserved after emdash merge"},
    "mcp":     {"status":"PASS","detail":"N servers"},
    "guide":   {"status":"PASS","detail":"home+repo guides present"},
    "repo_guides":{"status":"PASS","detail":"AGENTS.md + .claude present"}
  },
  "coexistence": {"emdash_hook_detected": true, "manifest_hooks_preserved": true, "worktree_permissions_intact": true}
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | verdict `INHERITED` — all dimensions pass |
| `1` | verdict `DEGRADED` — ≥1 dimension FAIL (fails closed) |
| `2` | verdict `BLOCKED` — no `<home>/.claude` (home deploy not run); env-check surfaces the prerequisite |
| `64` | usage error (bad flag) |

## Coexistence assertion (D3 detail — FR-007 / SC-003)

The probe simulates emdash's observed merge — appending `{ "type":"command", "command":"curl http://127.0.0.1:$EMDASH_HOOK_PORT/hook", <EMDASH_MARKER> }` to a hook event array — against the file emdash actually writes for the given scope (spec-review F3):

- **Home scope** (`~/.claude/settings.json`): this is where Manifest's **hooks** live (repo `settings.local.json` holds permissions only). The probe asserts every pre-existing Manifest hook entry survives the append → `manifest_hooks_preserved`.
- **Workspace scope** (`<worktree>/.claude/settings.local.json`): holds **permissions** (no Manifest hooks). The probe asserts the permissions block is not corrupted by the append → `worktree_permissions_intact`.

This is the deterministic core of the automated test; the manual smoke confirms the real app produces the same shape, writes to the expected scope, and that the hook actually fires under ACP mode.

## Verified by

- `tests/bats/emdash_inheritance.bats` drives the probe (`--json`) against `tests/bats/fixtures/emdash/` (a synthetic HOME + worktree + emdash-merged settings) and asserts each dimension + coexistence (FR-011a, SC-001, SC-003).
- `/env-check` invokes the probe live and renders the report (FR-010, SC-005).
- Manual smoke runbook in `quickstart.md` (FR-011b).
