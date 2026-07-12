# Phase 1 Data Model: emdash Support

This feature has no runtime data store. The "entities" are the configuration/verification artifacts the feature defines. Each maps to spec Key Entities and drives the contracts.

## E1 — emdash Project Config (`.emdash.json`)

Repo-root file emdash reads to configure worktree creation for this repository. The single per-repo surface added by this feature (FR-006).

| Field | Type | Purpose | This repo's value (finalized in impl) |
|-------|------|---------|----------------------------------------|
| `preservePatterns` | string[] (globs) | Untracked/ignored files copied into each new worktree | `guidance_local.yml`, `.env` (secrets — never committed) |
| `scripts.setup` | string | Command run once when a worktree is created | init submodules + `uv sync` (Python env) so `pytest`/`bats` work |
| `scripts.run` | string (optional) | Default run command | omitted (no single run target) |
| `scripts.teardown` | string (optional) | Cleanup on worktree removal | omitted |
| `shellSetup` | string (optional) | Prelude run in each PTY before the interactive shell | minimal/empty unless venv activation needed |

**Validation rules**:
- MUST be valid JSON (verified in CI: `python3 -c "import json; json.load(open('.emdash.json'))"`).
- `preservePatterns` MUST NOT include tracked files (e.g. NOT `.claude/settings.local.json`, which is tracked).
- `preservePatterns` MAY reference secret files; those files MUST remain gitignored (never committed by the repo).
- `scripts.setup` MUST be idempotent (a worktree may be re-set-up) and MUST fail closed.

## E2 — Inheritance Dimension (fixed checklist)

The closed set of things a Manifest-configured agent must inherit. Drives both the live diagnostic and the automated test (one row = one probe assertion). Adding a dimension = updating the probe + this table + the contract.

| ID | Dimension | Home source (`$HOME/.claude`) | Repo source (worktree) | Pass criterion |
|----|-----------|-------------------------------|------------------------|----------------|
| D1 | Skills | `skills/*/SKILL.md` | (committed repo skills, if any) | ≥1 resolvable `SKILL.md` reachable from the session |
| D2 | Subagents | `agents/*.md` | `.claude/agents/*.md` | Manifest subagent files reachable |
| D3 | Hooks | `settings.json` `hooks.*` | `.claude/settings.local.json` (permissions) | Manifest hooks present in resolved settings AND still present after an emdash hook-merge |
| D4 | MCP servers | `settings.json` `mcpServers` / `.mcp.json` | repo MCP config (if any) | Manifest MCP servers resolvable |
| D5 | Orchestration guide | `CLAUDE.md` (home guide) | `CLAUDE.md`, `.claude/CLAUDE.md` | guide files present/readable in the session context |
| D6 | Repo guides | — | `AGENTS.md`, committed `.claude/` | committed guidance present in the worktree checkout |

## E3 — emdash Launch-Env Fixture (test input)

Synthetic reproduction of how emdash launches an agent — the input the automated test feeds the probe (FR-011a). Lives under `tests/bats/fixtures/emdash/`.

| Component | Represents | Fixture form |
|-----------|-----------|--------------|
| Fake `HOME/.claude/` | The Manifest home deploy | `skills/`, `agents/`, `settings.json` (with Manifest hooks + mcpServers) |
| Fake worktree | A repo checkout in a worktree | `CLAUDE.md`, `AGENTS.md`, `.claude/` (incl. tracked `settings.local.json`) |
| Injected env | emdash's PTY env | `HOME`, `PATH`, `EMDASH_HOOK_PORT`, `EMDASH_PTY_ID`, `EMDASH_HOOK_NONCE` set |
| Merged settings | emdash's per-spawn hook write | a settings file with the emdash `Stop` hook (`curl …$EMDASH_HOOK_PORT/hook` + `EMDASH_MARKER`) appended alongside a pre-existing Manifest hook |

## E4 — Inheritance Probe Report (output)

Structured result emitted by `emdash_inherit_check.sh` (contract in `contracts/inheritance-probe.md`). Consumed by env-check (rendered into the health report) and the bats test (asserted).

| Field | Type | Meaning |
|-------|------|---------|
| per-dimension status | `PASS`/`FAIL`/`INFO` per D1–D6 | Whether each dimension resolves; D3 also reports "hooks preserved after emdash merge" |
| detail | string per dimension | Count/paths (e.g. "skills: 88 reachable") |
| coexistence note | string | Whether an emdash-injected hook was detected and Manifest hooks survived |
| overall verdict | `INHERITED` / `DEGRADED` / `BLOCKED` | `BLOCKED` if home deploy missing; `DEGRADED` if a dimension fails |
| exit code | int | `0` = all pass; non-zero = at least one FAIL (fails closed) |

## State transitions

None — all artifacts are static config/verification. The only "transition" is the probe verdict as a function of environment state: **BLOCKED** (no `~/.claude` home deploy) → **DEGRADED** (home deployed but a dimension missing) → **INHERITED** (all dimensions resolvable), mirrored by exit code.
