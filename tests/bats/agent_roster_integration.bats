#!/usr/bin/env bats
# End-to-end 6th-agent + hyphenated-agent integration proof (goal-task-E,
# "close out the agent-fleet single source of truth").
#
# Tasks A-D each already have their OWN unit-level 6th-agent acceptance test
# against an ISOLATED synthetic fixture:
#   - tests/python/test_reconcile_policy.py::test_sixth_agent_extends_fleet_via_config_only
#   - tests/bats/check_status.bats "6th roster-only agent is picked up by..."
#   - tests/bats/sync_skills.bats "6th roster-only agent is picked up by the
#     secondary sync loop..."
#   - tests/python/agents/test_cli.py::TestRosterDrivenSixthAgent /
#     TestHyphenatedRosterAgentName
#
# This file proves something none of those four do alone: that a SINGLE
# agent_roster.yml fixture -- written ONCE -- flows through ALL FOUR pieces
# of roster-derived infrastructure with zero source edits, and that the
# hyphenated-name fix in agents/cli.py holds under a REAL subprocess spawn
# (not just the in-process getattr()/argparse reproduction in test_cli.py).
#
# The four scripts read agent_roster.yml via two DIFFERENT mechanisms:
#   - reconcile_core.py / check_status.sh / sync-skills.sh: MANIFEST_AGENT_ROSTER
#     env var takes precedence (see each script's resolve_agent_roster_path()
#     equivalent).
#   - agents/config.py's load_agent_roster()/Config()/ServiceConfig() (used by
#     cli.py via parallel_agent.py): always HOME-relative
#     (~/.claude/config/agent_roster.yml, ~/.claude/config/services.yml) --
#     agent_roster.yml's own header documents this is a config-injection gap,
#     not a bug (cli.py has no MANIFEST_AGENT_ROSTER support).
# This test reconciles the two mechanisms onto ONE physical file: the roster
# lives at $HOME/.claude/config/agent_roster.yml (satisfying cli.py's
# HOME-relative default AND check_status.sh/sync-skills.sh's own "deployed
# home copy" fallback tier), and MANIFEST_AGENT_ROSTER is ALSO exported
# pointing at that exact same path (satisfying reconcile_core.py, which has
# no HOME-relative fallback). One file, two resolution paths, same bytes.
#
# The fixture carries two synthetic additions:
#   - "beta": a plain 6th agent (the four-piece proof; mirrors the "beta"
#     name already used by Task B/C's own bats fixtures).
#   - "test-agent": a HYPHENATED 7th agent -- the specific gap the Task D
#     re-reviewer flagged: a real, live `parallel_agent.py --test-agent-only`
#     subprocess spawn, not just the unit-level dest-mangling reproduction
#     already covered by test_cli.py::TestHyphenatedRosterAgentName.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'
load '../test_helper/stub_home_runtime.bash'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CHECK_STATUS="$REPO_ROOT/configs/claude/scripts/check_status.sh"
SYNC_SKILLS="$REPO_ROOT/configs/claude/scripts/sync-skills.sh"
RECONCILE_CORE="$REPO_ROOT/configs/claude/scripts/reconcile_core.py"
PARALLEL_AGENT="$REPO_ROOT/configs/claude/scripts/parallel_agent.py"

# The [4/4 cli.py] tests invoke parallel_agent.py, which is a deprecation shim
# routing to ~/.claude/.venv/bin/manifest. setup() stubs that from the repo's
# project venv when present; skip when it isn't (local run without `uv sync`).
require_home_runtime() {
    [[ -x "$HOME/.claude/.venv/bin/manifest" ]] ||
        skip "manifest home runtime not built (run: uv sync --project configs/claude)"
}

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"

    # Captured BEFORE any PATH restriction below -- always the real,
    # fully-featured interpreter (PyYAML, rich, ...) this repo's own tooling
    # runs under, regardless of what PATH a given `run` command uses for its
    # own subprocess/CLI discovery (shutil.which() inside parallel_agent.py
    # reads the CHILD process's PATH, which we control per-test; the
    # interpreter itself is resolved here, once, up front).
    PY_BIN="$(command -v python3)"

    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/agent_roster_integration.XXXXXX")
    ORIG_HOME="$HOME"
    ORIG_PATH="$PATH"
    export HOME="$TEST_DIR/home"
    mkdir -p "$HOME/.claude/config" "$HOME/.claude/skills"
    mkdir -p "$HOME/.beta/skills" "$HOME/.test-agent/skills"

    # The [4/4 cli.py] tests invoke the parallel_agent.py deprecation shim, which
    # routes to ~/.claude/.venv/bin/manifest. Stub that from the repo's project
    # venv (uv-synced, as CI does) via the shared helper; the [4/4] tests skip
    # when it isn't built (see require_home_runtime).
    if [[ -x "$REPO_ROOT/configs/claude/.venv/bin/manifest" ]]; then
        stub_home_manifest_runtime "$REPO_ROOT"
    fi

    ROSTER="$HOME/.claude/config/agent_roster.yml"
    cat > "$ROSTER" << 'EOF'
agents:
  claude:
    name: claude
    binary: claude
    home_dir: ~/.claude
    prompt_args: ["-p", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "claude auth status"
    enabled_default: true
  gemini:
    name: gemini
    binary: gemini
    home_dir: ~/.gemini
    prompt_args: ["-p", "{prompt}"]
    model_args: ["-m", "{model}"]
    auth_check: "gemini auth status"
    enabled_default: true
  cursor:
    name: cursor
    binary: cursor-agent
    home_dir: ~/.cursor
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "cursor-agent --version"
    enabled_default: true
  codex:
    name: codex
    binary: codex
    home_dir: ~/.codex
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "codex login status"
    enabled_default: true
  antigravity:
    name: antigravity
    binary: agy
    home_dir: ~/.antigravity
    prompt_args: ["--print", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "agy models"
    enabled_default: true
  beta:
    name: beta
    binary: beta-agent
    home_dir: ~/.beta
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "beta-agent --version"
    enabled_default: true
  test-agent:
    name: test-agent
    binary: echo
    home_dir: ~/.test-agent
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "echo ok"
    enabled_default: true
EOF
    export MANIFEST_AGENT_ROSTER="$ROSTER"

    cat > "$HOME/.claude/config/services.yml" << 'EOF'
services:
  claude:
    enabled: false
  gemini:
    enabled: false
  cursor:
    enabled: false
  codex:
    enabled: false
  antigravity:
    enabled: false
  beta:
    enabled: true
  test-agent:
    enabled: true
EOF

    MOCK_BIN="$TEST_DIR/mock_bin"
    mkdir -p "$MOCK_BIN"

    # beta's roster binary is "beta-agent" -- a stub CLI, not a real one.
    cat > "$MOCK_BIN/beta-agent" << 'EOF'
#!/bin/bash
case "$1" in
    --version) echo "beta-agent 1.0.0-mock"; exit 0 ;;
    *) echo "BETA-STUB-OUTPUT: $*"; exit 0 ;;
esac
EOF
    chmod +x "$MOCK_BIN/beta-agent"

    # GNU-coreutils `timeout` isn't guaranteed on macOS -- check_status.sh's
    # auth probes need it; drop the duration arg and exec the wrapped command.
    cat > "$MOCK_BIN/timeout" << 'EOF'
#!/bin/bash
shift
exec "$@"
EOF
    chmod +x "$MOCK_BIN/timeout"

    # rsync mock: log every invocation instead of doing real filesystem I/O
    # (mirrors sync_skills.bats).
    RSYNC_LOG="$TEST_DIR/rsync.log"
    export RSYNC_LOG
    cat > "$MOCK_BIN/rsync" << 'EOF'
#!/usr/bin/env bash
echo "rsync $*" >> "$RSYNC_LOG"
EOF
    chmod +x "$MOCK_BIN/rsync"

    export MANIFEST_ROOT="$TEST_DIR/repo"
    mkdir -p "$MANIFEST_ROOT/.apm/skills/demo-skill"
    echo "body" > "$MANIFEST_ROOT/.apm/skills/demo-skill/SKILL.md"

    export PATH="$MOCK_BIN:$PATH"
    unset OPENAI_API_KEY CODEX_HOME ANTHROPIC_API_KEY GOOGLE_API_KEY GEMINI_API_KEY
    unset MANIFEST_STATE_ROOT MANIFEST_TMP_DIR
    unset CLAUDE_STATE_DIR GEMINI_STATE_DIR CURSOR_STATE_DIR CODEX_STATE_DIR ANTIGRAVITY_STATE_DIR
}

teardown() {
    export HOME="$ORIG_HOME"
    export PATH="$ORIG_PATH"
    unset MANIFEST_AGENT_ROSTER MANIFEST_ROOT RSYNC_LOG
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        chmod -R u+w "$TEST_DIR" 2> /dev/null || true
        rm -rf "$TEST_DIR"
    fi
}

# ---------------------------------------------------------------------------
# 1/4: reconcile_core.py --list-tags
# ---------------------------------------------------------------------------

@test "[1/4 reconcile_core.py] --list-tags includes both the plain 6th agent and the hyphenated 7th agent" {
    run "$PY_BIN" "$RECONCILE_CORE" --list-tags
    assert_success
    assert_line "beta"
    assert_line "test-agent"
    # The 5 historical agents are still present too -- this is additive, not
    # a replacement of the known fleet.
    assert_line "claude"
    assert_line "cursor"
    assert_line "gemini"
    assert_line "codex"
    assert_line "antigravity"
}

# ---------------------------------------------------------------------------
# 2/4: check_status.sh (Enabled Services / CLI Tools)
# ---------------------------------------------------------------------------

@test "[2/4 check_status.sh] Enabled Services and CLI Tools enumerate the plain 6th agent correctly" {
    run bash "$CHECK_STATUS"
    assert_success
    # 7 roster agents now enumerated (5 historical + beta + test-agent); the
    # denominator itself proves the roster (not a hardcoded 5) drove the
    # count. Numerator is 2 (beta + test-agent, both enabled: true in
    # services.yml) now that the hyphenated-name identifier bug (see the
    # next test) is fixed and test-agent's enabled-state is read correctly
    # too -- pre-fix this was "(1/7)" because test-agent's own state was
    # always misread as disabled.
    assert_output --partial "Enabled Services (2/7):"
    assert_output --partial "Beta"
    refute_output --partial "Beta (disabled)"
    assert_output --partial "Beta CLI installed"
}

@test "[2/4 check_status.sh] a hyphenated roster agent is enumerated (CLI Tools) with correct enabled-state" {
    # check_status.sh's per-agent Enabled/CLI-Tools state is stored via
    # printf -v "\${r_name//-/_}_enabled" / "\${r_name//-/_}_installed" --
    # bash identifiers cannot contain '-', so a hyphenated name like
    # "test-agent" is sanitized to "test_agent" for the variable identifier
    # only (mirroring agents/cli.py's _dest() name-mangling; see
    # check_status.sh lines ~295, ~389 and the indirect-read sites at
    # ~304/~312/~439). services.yml enables test-agent, so it must report
    # enabled -- not the pre-fix "(disabled)" misread caused by printf -v
    # silently rejecting "test-agent_enabled" as "not a valid identifier".
    run bash "$CHECK_STATUS"
    assert_success
    assert_output --partial "Test-agent CLI installed"
    assert_output --partial "Test-agent"
    refute_output --partial "Test-agent (disabled)"
    # The other agents (crucially "beta", not adjacent to the bug) still
    # report correctly.
    assert_output --partial "Beta CLI installed"
    refute_output --partial "Beta (disabled)"
}

# ---------------------------------------------------------------------------
# 3/4: sync-skills.sh (secondary sync targets)
# ---------------------------------------------------------------------------

@test "[3/4 sync-skills.sh] secondary sync loop includes both the plain 6th agent and the hyphenated 7th agent's skills dir" {
    run bash "$SYNC_SKILLS"
    assert_success
    grep -q "\.beta/skills" "$RSYNC_LOG"
    grep -q "\.test-agent/skills" "$RSYNC_LOG"
    # claude is the primary target, never duplicated into the secondary loop.
    [ "$(grep -c "rsync -a" "$RSYNC_LOG")" -eq 3 ]
}

# ---------------------------------------------------------------------------
# 4/4: agents/cli.py (via parallel_agent.py) -- flags + a REAL live dispatch
# ---------------------------------------------------------------------------

@test "[4/4 cli.py] --help advertises working flags for both the plain 6th agent and the hyphenated 7th agent" {
    require_home_runtime
    run "$PY_BIN" "$PARALLEL_AGENT" --help
    assert_success
    assert_output --partial "--beta-only"
    assert_output --partial "--no-beta"
    assert_output --partial "--beta-model"
    assert_output --partial "--test-agent-only"
    assert_output --partial "--no-test-agent"
    assert_output --partial "--test-agent-model"
}

@test "[4/4 cli.py] --beta-only dispatches a REAL live CLIAgent subprocess (plain 6th agent)" {
    require_home_runtime
    run "$PY_BIN" "$PARALLEL_AGENT" --beta-only --no-synthesize --timeout 15 --json "ping"
    assert_success
    assert_output --partial '"beta"'
    assert_output --partial '"status": "complete"'
    assert_output --partial "BETA-STUB-OUTPUT: ping"
}

@test "[4/4 cli.py] --test-agent-only dispatches a REAL live CLIAgent subprocess (hyphenated 7th agent) -- closes the Task D live-run gap" {
    # This is the specific gap the Task D re-reviewer flagged: prior coverage
    # (test_cli.py::TestHyphenatedRosterAgentName) exercises the dest-mangling
    # fix (_dest()) via build_parser()/resolve_enabled_agents() directly, in
    # process, with a fabricated roster dict -- never a real `python3
    # parallel_agent.py --gemini-pro-only ...` process spawn. Here the roster
    # is read from disk (agent_roster.yml, HOME-relative), argv is parsed by
    # a genuine argparse.ArgumentParser, and a real subprocess.exec of the
    # stub binary ("echo", matching Task D's own echo-as-CLI pattern) runs
    # end to end -- proving the fix holds under a real process boundary, not
    # just the in-process reproduction.
    require_home_runtime
    run "$PY_BIN" "$PARALLEL_AGENT" --test-agent-only --no-synthesize --timeout 15 --json "ping"
    assert_success
    assert_output --partial '"test-agent"'
    assert_output --partial '"status": "complete"'
    assert_output --partial '"output": "ping"'
}
