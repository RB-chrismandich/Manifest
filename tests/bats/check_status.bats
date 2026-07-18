#!/usr/bin/env bats
# Tests for configs/claude/scripts/check_status.sh
# services.yml parsing, CLI detection, auth probes, state dirs, overall status
#
# Hermetic strategy:
#   - HOME is redirected to a mktemp sandbox (script reads ~/.claude/config/services.yml
#     and defaults MANIFEST_STATE_ROOT to $HOME/.manifest)
#   - PATH is reduced to MOCK_BIN + system dirs so real claude/gemini/cursor/codex
#     (typically in /opt/homebrew or ~/.local) are never found unless mocked
#   - `timeout` is mocked (GNU coreutils, not guaranteed on macOS) so auth probes
#     are deterministic

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../configs/claude/scripts/check_status.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/check_status_test.XXXXXX")

    ORIG_HOME="$HOME"
    export HOME="$TEST_DIR/home"
    mkdir -p "$HOME/.claude/config"

    MOCK_BIN="$TEST_DIR/mock_bin"
    mkdir -p "$MOCK_BIN"

    # Restricted PATH: mocks first, then system coreutils only (hides real agent CLIs)
    ORIG_PATH="$PATH"
    export PATH="$MOCK_BIN:/usr/bin:/bin"

    # Deterministic `timeout`: drop the duration arg, exec the wrapped command
    cat > "$MOCK_BIN/timeout" << 'EOF'
#!/bin/bash
shift
exec "$@"
EOF
    chmod +x "$MOCK_BIN/timeout"

    # Keep auth env out of the sandbox
    unset OPENAI_API_KEY CODEX_HOME
    unset MANIFEST_STATE_ROOT MANIFEST_TMP_DIR
    unset CLAUDE_STATE_DIR GEMINI_STATE_DIR CURSOR_STATE_DIR CODEX_STATE_DIR ANTIGRAVITY_STATE_DIR
    unset MANIFEST_AGENT_ROSTER
}

teardown() {
    export HOME="$ORIG_HOME"
    export PATH="$ORIG_PATH"
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        chmod -R u+w "$TEST_DIR" 2> /dev/null || true
        rm -rf "$TEST_DIR"
    fi
}

# --- Fixture helpers ---

write_services_yml() {
    # write_services_yml <claude> <gemini> <cursor> <codex> [antigravity] [graphify]
    cat > "$HOME/.claude/config/services.yml" << EOF
services:
  claude:
    enabled: $1
  gemini:
    enabled: $2
  cursor:
    enabled: $3
  codex:
    enabled: $4
  antigravity:
    enabled: ${5:-false}
  graphify:
    enabled: ${6:-false}
EOF
}

make_mock_cli() {
    # make_mock_cli <name> [auth_exit_code]
    local name="$1" auth_rc="${2:-0}"
    cat > "$MOCK_BIN/$name" << EOF
#!/bin/bash
case "\$1" in
    auth) exit $auth_rc ;;
    --version) echo "$name 1.0.0-mock"; exit 0 ;;
    *) exit 0 ;;
esac
EOF
    chmod +x "$MOCK_BIN/$name"
}

# --- services.yml parsing ---

@test "detects services.yml when present" {
    write_services_yml true true true true
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "services.yml found"
}

@test "fixture with one enabled and one disabled service is reflected correctly" {
    write_services_yml true false false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    # enabled service shows plain name; disabled services get the (disabled) suffix
    assert_output --partial "Claude"
    refute_output --partial "Claude (disabled)"
    assert_output --partial "Gemini (disabled)"
    assert_output --partial "Cursor (disabled)"
    assert_output --partial "Codex (disabled)"
}

@test "counts enabled services (1/5)" {
    write_services_yml true false false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Enabled Services (1/5):"
}

@test "counts enabled services (5/5)" {
    # graphify (6th arg) enabled too, so no "(disabled)" marker appears; the count
    # stays 5/5 because graphify is a tool, not a counted orchestration agent (D4).
    write_services_yml true true true true true true
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Enabled Services (5/5):"
    refute_output --partial "(disabled)"
}

@test "warns when fewer than 2 services are enabled" {
    write_services_yml true false false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Minimum 2 services needed for parallel orchestration"
}

@test "no minimum-services warning when 2 services are enabled" {
    write_services_yml true true false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    refute_output --partial "Minimum 2 services needed"
}

@test "missing services.yml is handled gracefully with bootstrap hint and exit 0" {
    # no services.yml written
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "services.yml not found"
    assert_output --partial "Run: ./bootstrap.sh"
}

# --- CLI tool detection (mocked via MOCK_BIN on PATH) ---

@test "reports installed CLIs from PATH" {
    write_services_yml true true false false
    make_mock_cli claude
    make_mock_cli gemini
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Claude CLI installed"
    assert_output --partial "Gemini CLI installed"
}

@test "reports missing CLIs with install hints" {
    write_services_yml true true true true
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Claude CLI not installed"
    # assert_output --partial "npm install -g @anthropic-ai/claude-code"
    assert_output --partial "Gemini CLI not installed"
    assert_output --partial "cursor-agent not available (optional)"
    assert_output --partial "Codex CLI not installed"
}

# --- Graphify (managed tool, NOT a parallel-orchestration agent) ---

@test "reports graphify installed when enabled and CLI present" {
    write_services_yml true false false false false true
    make_mock_cli graphify
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Graphify CLI installed"
}

@test "reports graphify not installed when enabled but CLI missing" {
    write_services_yml true false false false false true
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Graphify CLI not installed"
}

@test "reports graphify disabled when toggled off" {
    write_services_yml true false false false false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Graphify (disabled)"
}

@test "graphify does not count toward the orchestration agent total (D4)" {
    # claude + gemini = 2 agents; graphify enabled must NOT make it 3/6.
    write_services_yml true true false false false true
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Enabled Services (2/5):"
    refute_output --partial "/6"
}

@test "verbose mode shows CLI location and version" {
    write_services_yml true false false false
    make_mock_cli claude
    run bash "$SCRIPT_UNDER_TEST" --verbose
    assert_success
    assert_output --partial "Location: $MOCK_BIN/claude"
    assert_output --partial "claude 1.0.0-mock"
}

# --- Authentication ---

@test "reports claude/gemini authenticated when auth status succeeds" {
    write_services_yml true true false false
    make_mock_cli claude 0
    make_mock_cli gemini 0
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Claude authenticated"
    assert_output --partial "Gemini authenticated"
}

@test "reports authentication unknown when auth status fails" {
    write_services_yml true false false false
    make_mock_cli claude 1
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Claude authentication unknown"
    assert_output --partial "Verify: claude auth status"
}

@test "codex authenticated via OPENAI_API_KEY" {
    write_services_yml false false false true
    make_mock_cli codex
    export OPENAI_API_KEY="sk-test"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Codex authenticated"
}

@test "codex authenticated via auth.json in CODEX_HOME" {
    write_services_yml false false false true
    make_mock_cli codex
    mkdir -p "$TEST_DIR/codex_home"
    touch "$TEST_DIR/codex_home/auth.json"
    export CODEX_HOME="$TEST_DIR/codex_home"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Codex authenticated"
}

@test "codex authentication unknown without key or auth.json" {
    write_services_yml false false false true
    make_mock_cli codex
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Codex authentication unknown"
}

make_mock_agy() {
    # make_mock_agy [models_exit_code]
    local models_rc="${1:-0}"
    cat > "$MOCK_BIN/agy" << EOF
#!/bin/bash
case "\$1" in
    models) exit $models_rc ;;
    --version) echo "agy 1.0.0-mock"; exit 0 ;;
    *) exit 0 ;;
esac
EOF
    chmod +x "$MOCK_BIN/agy"
}

@test "antigravity authenticated when 'agy models' succeeds" {
    write_services_yml false false false false true
    make_mock_agy 0
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Antigravity authenticated"
}

@test "antigravity authentication unknown when 'agy models' fails" {
    write_services_yml false false false false true
    make_mock_agy 1
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Antigravity authentication unknown"
    assert_output --partial "Verify: agy models"
}

# --- Auth probe timeout fallback (no GNU coreutils on PATH) ---

@test "auth probe is bounded by the pure-bash fallback when no timeout binary exists" {
    # Regression: run_with_timeout was a no-op without timeout(1)/gtimeout(1),
    # so a slow `gemini auth status` (~60s) ran unbounded and made the whole
    # readiness check take ~196s on stock macOS. The fallback must cap it at ~3s.
    write_services_yml true true false false
    make_mock_cli claude 0
    # gemini whose `auth` hangs well past the 3s bound
    cat > "$MOCK_BIN/gemini" << 'EOF'
#!/bin/bash
case "$1" in
    auth) sleep 30 ;;
    --version) echo "gemini 1.0.0-mock"; exit 0 ;;
    *) exit 0 ;;
esac
EOF
    chmod +x "$MOCK_BIN/gemini"

    local start=$SECONDS
    run env CHECK_STATUS_NO_TIMEOUT_CMD=1 bash "$SCRIPT_UNDER_TEST"
    local elapsed=$(( SECONDS - start ))

    assert_success
    # slow probe is killed -> reported as unknown, not hung
    assert_output --partial "Gemini authentication unknown"
    [ "$elapsed" -lt 15 ]
}

@test "gemini auth uses the fast credential check, not the slow CLI probe" {
    # oauth_creds.json present must short-circuit to authenticated WITHOUT
    # calling `gemini auth status` (which would exit 1 here -> "unknown").
    write_services_yml true true false false
    make_mock_cli claude 0
    make_mock_cli gemini 1
    mkdir -p "$HOME/.gemini"
    echo '{}' > "$HOME/.gemini/oauth_creds.json"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Gemini authenticated"
    refute_output --partial "Gemini authentication unknown"
}

# --- State directory resolution (MANIFEST_STATE_ROOT seam) ---

@test "MANIFEST_STATE_ROOT is honored and state dirs are created" {
    write_services_yml true true false false
    export MANIFEST_STATE_ROOT="$TEST_DIR/custom_state"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Manifest state root ready: $TEST_DIR/custom_state"
    [ -d "$TEST_DIR/custom_state/tmp" ]
    [ -d "$TEST_DIR/custom_state/claude" ]
    [ -d "$TEST_DIR/custom_state/gemini" ]
    [ -d "$TEST_DIR/custom_state/cursor" ]
    [ -d "$TEST_DIR/custom_state/codex" ]
    [ -d "$TEST_DIR/custom_state/antigravity" ]
}

@test "antigravity state dir env override is honored (verbose, symmetry with codex/gemini/cursor)" {
    write_services_yml false false false false true
    export ANTIGRAVITY_STATE_DIR="$TEST_DIR/alt_antigravity_state"
    run bash "$SCRIPT_UNDER_TEST" --verbose
    assert_success
    assert_output --partial "$TEST_DIR/alt_antigravity_state"
    [ -d "$TEST_DIR/alt_antigravity_state" ]
}

@test "defaults state root to HOME/.manifest" {
    write_services_yml true false false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Manifest state root ready: $HOME/.manifest"
    [ -d "$HOME/.manifest/tmp" ]
}

@test "per-service state dir env overrides are honored (verbose)" {
    write_services_yml true false false false
    export CLAUDE_STATE_DIR="$TEST_DIR/alt_claude_state"
    run bash "$SCRIPT_UNDER_TEST" --verbose
    assert_success
    assert_output --partial "$TEST_DIR/alt_claude_state"
    [ -d "$TEST_DIR/alt_claude_state" ]
}

@test "reports unwritable state dir" {
    if [[ "$(id -u)" -eq 0 ]]; then
        skip "root ignores directory permissions"
    fi
    write_services_yml true false false false
    export MANIFEST_STATE_ROOT="$TEST_DIR/ro_state"
    mkdir -p "$TEST_DIR/ro_state"
    chmod 500 "$TEST_DIR/ro_state"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Not writable:"
    refute_output --partial "Manifest state root ready:"
}

# --- Overall status / agent readiness ---

@test "system ready when 2 agents are enabled and installed" {
    write_services_yml true true false false
    make_mock_cli claude
    make_mock_cli gemini
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "System ready for parallel orchestration (2 agents available)"
}

@test "limited functionality when only 1 agent is available" {
    # gemini enabled but not installed; claude installed and enabled
    write_services_yml true true false false
    make_mock_cli claude
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Limited functionality (only 1 agent available)"
}

@test "not operational when no agents are available and exit code is still 0" {
    write_services_yml false false false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "System not operational (no agents available)"
}

@test "installed but disabled service does not count as a working agent" {
    write_services_yml false false false false
    make_mock_cli claude
    make_mock_cli gemini
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "System not operational"
}

# --- Output shape ---

@test "output includes header, section labels, and documentation pointers" {
    write_services_yml true true false false
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Parallel Agent System Health Check"
    assert_output --partial "Configuration:"
    assert_output --partial "CLI Tools:"
    assert_output --partial "Authentication:"
    assert_output --partial "State Directories:"
    assert_output --partial "Overall Status:"
    assert_output --partial "Documentation:"
    assert_output --partial "docs/TROUBLESHOOTING.md"
}

@test "quick test hint shown only when at least one agent is available" {
    write_services_yml true false false false
    make_mock_cli claude
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Quick Test:"
    assert_output --partial "parallel_agent.py --json"

    write_services_yml false false false false
    rm -f "$MOCK_BIN/claude"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    refute_output --partial "Quick Test:"
}

# ---------------------------------------------------------------------------
# Model Pins summary honesty: SKIPPED providers must not read as a green
# "complete" (the OAuth-only false-green found in the 2026-06-11 validation).
# ---------------------------------------------------------------------------

@test "model pins summary warns when providers were skipped (no false green)" {
    write_services_yml true true false false
    # Sandbox PATH has no agent CLIs and no API keys -> claude/gemini SKIPPED
    ANTHROPIC_API_KEY="" GOOGLE_API_KEY="" run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "unverified"
    refute_output --partial "Model pin check complete (stale pins above, if any)"
}

# ---------------------------------------------------------------------------
# agent_roster.yml-driven enumeration (Task 26): Enabled Services and CLI
# Tools are derived from the registry, not a hardcoded 5-agent list.
# Mirrors the acceptance-test pattern from
# tests/python/test_reconcile_policy.py::test_sixth_agent_extends_fleet_via_config_only
# -- a synthetic 6th agent added ONLY to a fresh, env-var-pointed roster
# fixture (never the real registry) must be picked up with zero changes to
# check_status.sh.
# ---------------------------------------------------------------------------

write_sixth_agent_roster() {
    cat > "$TEST_DIR/agent_roster.yml" << 'EOF'
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
EOF
}

@test "6th roster-only agent is picked up by the Enabled Services count without a script edit" {
    write_sixth_agent_roster
    # services.yml also needs a "beta" block -- write_services_yml only knows
    # the 5 historical agents, so this test writes it directly.
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
  graphify:
    enabled: false
  beta:
    enabled: true
EOF
    export MANIFEST_AGENT_ROSTER="$TEST_DIR/agent_roster.yml"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    # 6 agents now enumerated (5 historical + beta), 1 enabled -- the
    # denominator itself proves the roster (not a hardcoded 5) drove the count.
    assert_output --partial "Enabled Services (1/6):"
    assert_output --partial "Beta"
    refute_output --partial "Beta (disabled)"
}

@test "6th roster-only agent is picked up by the CLI Tools check without a script edit" {
    write_sixth_agent_roster
    cat > "$MOCK_BIN/beta-agent" << 'EOF'
#!/bin/bash
case "$1" in
    --version) echo "beta-agent 1.0.0-mock"; exit 0 ;;
    *) exit 0 ;;
esac
EOF
    chmod +x "$MOCK_BIN/beta-agent"
    write_services_yml true false false false
    export MANIFEST_AGENT_ROSTER="$TEST_DIR/agent_roster.yml"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Beta CLI installed"
}

@test "6th roster-only agent without its binary installed reports not-installed, not a crash" {
    write_sixth_agent_roster
    write_services_yml false false false false
    export MANIFEST_AGENT_ROSTER="$TEST_DIR/agent_roster.yml"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output --partial "Beta CLI not installed (optional)"
}

@test "total roster-parse failure falls back to the 5 historical hardcoded agents, not 0/0" {
    # Reproduce the reviewer's exact total-failure scenario: MANIFEST_AGENT_ROSTER
    # points at a file that exists but is garbage -- it fails BOTH the
    # python3+PyYAML parse (yaml.safe_load succeeds but yields a bare string,
    # not a dict, so data.get("agents") raises and is swallowed) AND the awk
    # fallback parse (no "^agents:" line for it to key off of) -- combined
    # with this suite's already-restricted PATH (MOCK_BIN:/usr/bin:/bin, whose
    # /usr/bin/python3 has no PyYAML -- see setup()). Before agent_roster.yml
    # existed, this script always reported the true state of the 5 hardcoded
    # agents; a bare roster-read failure must not regress that to "0/0".
    cat > "$TEST_DIR/agent_roster.yml" << 'EOF'
this is not a valid agent roster file at all
EOF
    export MANIFEST_AGENT_ROSTER="$TEST_DIR/agent_roster.yml"

    make_mock_cli claude
    make_mock_cli gemini
    write_services_yml true true false false

    run bash "$SCRIPT_UNDER_TEST"
    assert_success

    # Denominator is the 5 historical agents, not 0 -- proves the third
    # fallback tier populated ROSTER_NAMES instead of leaving it empty.
    assert_output --partial "Enabled Services (2/5):"
    refute_output --partial "Enabled Services (0/0)"
    refute_output --partial "Claude (disabled)"
    refute_output --partial "Gemini (disabled)"
    assert_output --partial "Cursor (disabled)"
    assert_output --partial "Codex (disabled)"
    assert_output --partial "Antigravity (disabled)"

    # CLI Tools section reflects real installed state, not an empty roster.
    assert_output --partial "Claude CLI installed"
    assert_output --partial "Gemini CLI installed"

    # services.yml's real enabled state (claude+gemini) drives a real "ready"
    # verdict -- not the false "no agents available" the bug produced.
    assert_output --partial "System ready for parallel orchestration (2 agents available)"
    refute_output --partial "System not operational (no agents available)"
}
