# Quickstart: Verify Graphify Integration

**Feature**: 364-graphify-integration

Manual verification of the acceptance scenarios after implementation. Run from the repo root.

## 1. Lint & unit tests (CI mirror)

```bash
shellcheck bootstrap.sh bootstrap/lib/*.sh configs/claude/scripts/check_status.sh
yamllint configs/claude/config/services.yml
bats tests/bats/bootstrap_services.bats tests/bats/check_status.bats
pytest tests/python/agents/test_config.py
```
Expect: all green, including the new graphify cases.

## 2. Default-on toggle (US1 / SC-001)

```bash
./bootstrap.sh --skip-auth --force          # standard run, no graphify flag
grep -A3 '^  graphify:' ~/.claude/config/services.yml   # → enabled: true
command -v graphify && graphify --version    # CLI present
ls ~/.claude/skills/graphify/SKILL.md        # skill vendored + deployed
for d in cursor gemini codex antigravity; do readlink ~/.$d/skills 2>/dev/null; done   # symlinks → ~/.claude/skills (for enabled assistants)
```

## 3. Idempotency (SC-003)

```bash
./bootstrap.sh --skip-auth --force           # second run
# Expect: "uv ... already installed" / "graphifyy already installed" — no duplicate work, no errors.
```

## 4. Opt-out (US2 / SC-002)

```bash
./bootstrap.sh --disable-graphify --skip-auth --force
grep -A3 '^  graphify:' ~/.claude/config/services.yml   # → enabled: false
ls ~/.claude/skills/graphify 2>/dev/null || echo "skill absent (expected)"
./bootstrap.sh --skip-auth --force            # flag-less re-run
grep -A3 '^  graphify:' ~/.claude/config/services.yml   # → still false (persisted, US2-AC3)
```

## 5. Health-check (US3 / SC-004)

```bash
configs/claude/scripts/check_status.sh        # graphify listed: enabled + installed/not-installed
```
Re-enable and confirm enabled-and-ready; temporarily rename the `graphify` binary to confirm enabled-but-not-installed reports a hint.

## 6. Skill behavior with CLI absent (FR-011 edge case)

With graphify uninstalled, invoke `/graphify .` in Claude Code → expect a clear "graphify not installed, run `./bootstrap.sh --enable-graphify`" message, not a crash.

## 7. Failure isolation (SC-005)

Simulate an offline install (e.g., break `uv` on PATH) and run `./bootstrap.sh` → graphify install warns and is skipped; the rest of bootstrap completes successfully and exits 0.

## 8. Docs discoverability (SC-006)

Confirm graphify appears in `README.md`, `docs/GETTING_STARTED.md`, `docs/CONFIGURATION.md`, `docs/COMMANDS.md`, root `CLAUDE.md`, and `AGENTS.md`, including how to enable/disable, invoke, and troubleshoot.
