#!/usr/bin/env bats
# Tests for bootstrap/lib/auth.sh — auth-status detection branches
# (currently only transitively covered via bootstrap.sh). All CLIs are
# stubbed via PATH shims in a temp dir; no real auth flows, no network.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
COMMON_LIB="$REPO_ROOT/bootstrap/lib/common.sh"
AUTH_LIB="$REPO_ROOT/bootstrap/lib/auth.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/auth_test.XXXXXX")
    FAKE_HOME="$TEST_DIR/home"
    FAKE_BIN="$TEST_DIR/bin"
    mkdir -p "$FAKE_HOME" "$FAKE_BIN"
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Write an executable stub named $1 into FAKE_BIN that exits with $2
# (default 0) and echoes anything passed to it.
make_stub() {
    local name="$1"
    local exit_code="${2:-0}"
    cat > "$FAKE_BIN/$name" << EOF
#!/bin/bash
exit $exit_code
EOF
    chmod +x "$FAKE_BIN/$name"
}

# Source common.sh + auth.sh inside a fresh bash with a stubbed PATH/HOME so
# each test gets an isolated environment. Extra env assignments/commands are
# appended as $1.
run_in_harness() {
    bash -c "
        set -u
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        HOME='$FAKE_HOME'
        PATH='$FAKE_BIN:/usr/bin:/bin'
        TIMEOUT_CMD=''
        GOOGLE_API_KEY=''
        GEMINI_API_KEY=''
        source '$COMMON_LIB'
        source '$AUTH_LIB'
        $1
    "
}

@test "check_claude_auth returns success without checking when ENABLE_CLAUDE is false" {
    run run_in_harness '
        ENABLE_CLAUDE=false
        check_claude_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "exit=0"
    refute_output --partial "Checking Claude Code"
}

@test "check_claude_auth warns and returns 1 when the CLI is not installed" {
    run run_in_harness '
        ENABLE_CLAUDE=true
        check_claude_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Claude Code CLI not installed"
    assert_output --partial "exit=1"
}

@test "check_claude_auth succeeds when an auth token file is present" {
    make_stub claude 0
    mkdir -p "$FAKE_HOME/.claude-code"
    echo '{}' > "$FAKE_HOME/.claude-code/auth.json"
    run run_in_harness '
        ENABLE_CLAUDE=true
        check_claude_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Claude Code is authenticated"
    assert_output --partial "exit=0"
}

@test "check_claude_auth errors when the CLI is installed but no auth file or timeout fallback succeeds" {
    make_stub claude 1
    run run_in_harness '
        ENABLE_CLAUDE=true
        check_claude_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Claude Code is NOT authenticated"
    assert_output --partial "exit=1"
}

@test "check_gemini_auth succeeds via an API key in the environment" {
    make_stub gemini 0
    run run_in_harness '
        ENABLE_GEMINI=true
        GEMINI_API_KEY="fake-key"
        check_gemini_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Gemini CLI is authenticated (API key)"
    assert_output --partial "exit=0"
}

@test "check_gemini_auth succeeds via an OAuth credentials file" {
    make_stub gemini 0
    mkdir -p "$FAKE_HOME/.gemini"
    echo '{}' > "$FAKE_HOME/.gemini/oauth_creds.json"
    run run_in_harness '
        ENABLE_GEMINI=true
        check_gemini_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Gemini CLI is authenticated (OAuth)"
    assert_output --partial "exit=0"
}

@test "check_gemini_auth declines setup and errors when unauthenticated and user says no" {
    make_stub gemini 0
    run bash -c "
        RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
        GOOGLE_API_KEY='' GEMINI_API_KEY=''
        HOME='$FAKE_HOME'
        PATH='$FAKE_BIN:\$PATH'
        source '$COMMON_LIB'
        source '$AUTH_LIB'
        ENABLE_GEMINI=true
        check_gemini_auth
        echo \"exit=\$?\"
    " <<< "n"
    assert_success
    assert_output --partial "Gemini CLI is NOT authenticated"
    assert_output --partial "Gemini CLI remains unauthenticated"
    assert_output --partial "exit=1"
}

@test "check_gemini_auth warns and returns 1 when the CLI is not installed" {
    run run_in_harness '
        ENABLE_GEMINI=true
        check_gemini_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Gemini CLI not installed"
    assert_output --partial "exit=1"
}

@test "check_gh_auth returns success without checking when ENABLE_GH is false" {
    run run_in_harness '
        ENABLE_GH=false
        check_gh_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "exit=0"
    refute_output --partial "Checking GitHub CLI"
}

@test "check_gh_auth succeeds when gh auth status exits 0" {
    make_stub gh 0
    run run_in_harness '
        ENABLE_GH=true
        check_gh_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "GitHub CLI is authenticated"
    assert_output --partial "exit=0"
}

@test "check_gh_auth errors when gh auth status exits nonzero" {
    make_stub gh 1
    run run_in_harness '
        ENABLE_GH=true
        check_gh_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "GitHub CLI is NOT authenticated"
    assert_output --partial "exit=1"
}

@test "check_glab_auth succeeds when glab auth status exits 0" {
    make_stub glab 0
    run run_in_harness '
        ENABLE_GLAB=true
        check_glab_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "GitLab CLI is authenticated"
    assert_output --partial "exit=0"
}

@test "check_glab_auth warns and returns 1 when the CLI is not installed" {
    run run_in_harness '
        ENABLE_GLAB=true
        check_glab_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "GitLab CLI not installed"
    assert_output --partial "exit=1"
}

# --- check_antigravity_auth (agy) ---

# Write an executable `agy` stub that responds to `models` with $2 (default 0).
make_agy_stub() {
    local exit_code="${1:-0}"
    cat > "$FAKE_BIN/agy" << EOF
#!/bin/bash
case "\$1" in
    models) exit $exit_code ;;
    *) exit 0 ;;
esac
EOF
    chmod +x "$FAKE_BIN/agy"
}

@test "check_antigravity_auth returns success without checking when ENABLE_ANTIGRAVITY is false" {
    run run_in_harness '
        ENABLE_ANTIGRAVITY=false
        check_antigravity_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "exit=0"
    refute_output --partial "Checking Antigravity"
}

@test "check_antigravity_auth warns and returns 1 when the CLI is not installed" {
    run run_in_harness '
        ENABLE_ANTIGRAVITY=true
        check_antigravity_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Antigravity CLI (agy) not installed"
    assert_output --partial "exit=1"
}

@test "check_antigravity_auth succeeds when 'agy models' exits 0" {
    make_agy_stub 0
    run run_in_harness '
        ENABLE_ANTIGRAVITY=true
        TIMEOUT_CMD=""
        check_antigravity_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Antigravity CLI is authenticated"
    assert_output --partial "exit=0"
}

@test "check_antigravity_auth errors when 'agy models' exits nonzero" {
    make_agy_stub 1
    run run_in_harness '
        ENABLE_ANTIGRAVITY=true
        TIMEOUT_CMD=""
        check_antigravity_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Antigravity CLI is NOT authenticated"
    assert_output --partial "exit=1"
}

@test "check_antigravity_auth uses TIMEOUT_CMD when available" {
    # A fake timeout(1) that drops the duration arg and execs the wrapped command,
    # proving check_antigravity_auth actually routes the probe through TIMEOUT_CMD.
    cat > "$FAKE_BIN/timeout" << 'EOF'
#!/bin/bash
shift
exec "$@"
EOF
    chmod +x "$FAKE_BIN/timeout"
    make_agy_stub 0
    run run_in_harness '
        ENABLE_ANTIGRAVITY=true
        TIMEOUT_CMD="timeout"
        check_antigravity_auth
        echo "exit=$?"
    '
    assert_success
    assert_output --partial "Antigravity CLI is authenticated"
}

@test "check_antigravity_auth bounds a hanging 'agy models' without a timeout binary (macOS-safe fallback)" {
    # Regression guard for the macOS-safe bound requirement: no timeout(1)/
    # gtimeout(1) on PATH must still cap the probe instead of hanging bootstrap.
    cat > "$FAKE_BIN/agy" << 'EOF'
#!/bin/bash
case "$1" in
    models) sleep 30; exit 0 ;;
    *) exit 0 ;;
esac
EOF
    chmod +x "$FAKE_BIN/agy"

    local start=$SECONDS
    run run_in_harness '
        ENABLE_ANTIGRAVITY=true
        TIMEOUT_CMD=""
        check_antigravity_auth
        echo "exit=$?"
    '
    local elapsed=$(( SECONDS - start ))

    assert_success
    assert_output --partial "Antigravity CLI is NOT authenticated"
    [ "$elapsed" -lt 15 ]
}
