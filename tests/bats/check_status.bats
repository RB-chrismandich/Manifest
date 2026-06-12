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
    unset CLAUDE_STATE_DIR GEMINI_STATE_DIR CURSOR_STATE_DIR CODEX_STATE_DIR
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
    # write_services_yml <claude> <gemini> <cursor> <codex> [antigravity]
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
    write_services_yml true true true true true
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
    assert_output --partial "npm install -g @anthropic-ai/claude-code"
    assert_output --partial "Gemini CLI not installed"
    assert_output --partial "Cursor not available (optional)"
    assert_output --partial "Codex CLI not installed"
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
