#!/usr/bin/env bats
# Tests for bootstrap/lib/install.sh — uv_sync_home_runtime()

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INSTALL_LIB="$REPO_ROOT/bootstrap/lib/install.sh"
COMMON_LIB="$REPO_ROOT/bootstrap/lib/common.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/uv_sync_home_runtime.XXXXXX")
    export HOME="$SANDBOX/home"
    export TARGET_DIR="$HOME/.claude"
    export SCRIPT_DIR="$REPO_ROOT"
    mkdir -p "$TARGET_DIR/config" "$HOME/.local/bin"

    MOCK_BIN="$SANDBOX/bin"
    mkdir -p "$MOCK_BIN"
    export UV_LOG="$SANDBOX/uv.log"
    : > "$UV_LOG"
    export PLAYWRIGHT_LOG="$SANDBOX/playwright.log"
    : > "$PLAYWRIGHT_LOG"

    cat > "$MOCK_BIN/uv" <<'STUB'
#!/usr/bin/env bash
echo "uv $*" >> "$UV_LOG"
if [[ "$1" == "sync" ]]; then
  exit 0
fi
exit 0
STUB
    chmod +x "$MOCK_BIN/uv"
    export PATH="$MOCK_BIN:$PATH"

    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { echo "WARN: $*"; }
    print_error()   { echo "ERR: $*"; }
    # shellcheck disable=SC1090
    source "$COMMON_LIB"
    # shellcheck disable=SC1090
    source "$INSTALL_LIB"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

_write_services() {
    cat > "$TARGET_DIR/config/services.yml" <<EOF
services:
  smoke:
    enabled: ${1:-false}
  browser_use:
    enabled: ${2:-false}
EOF
}

_install_playwright_stub() {
    mkdir -p "$TARGET_DIR/.venv/bin"
    cat > "$TARGET_DIR/.venv/bin/playwright" <<'STUB'
#!/usr/bin/env bash
echo "playwright $*" >> "$PLAYWRIGHT_LOG"
exit 0
STUB
    chmod +x "$TARGET_DIR/.venv/bin/playwright"
}

@test "skips gracefully when uv is not available" {
    local nobin="$SANDBOX/nobin"
    mkdir -p "$nobin"
    run env HOME="$HOME" TARGET_DIR="$TARGET_DIR" SCRIPT_DIR="$SCRIPT_DIR" PATH="$nobin:/usr/bin:/bin" bash -c '
        RED="" GREEN="" BLUE="" YELLOW="" CYAN="" BOLD="" NC=""
        print_warning() { echo "WARN: $*"; }
        # shellcheck disable=SC1090
        source "'"$COMMON_LIB"'"
        # shellcheck disable=SC1090
        source "'"$INSTALL_LIB"'"
        uv_sync_home_runtime
    '
    assert_success
    assert_output --partial "uv not found"
    [[ ! -f "$HOME/.local/bin/manifest" ]]
}

@test "runs uv sync against TARGET_DIR with no groups by default" {
    run uv_sync_home_runtime
    assert_success
    grep -q 'uv sync --project '"$TARGET_DIR" "$UV_LOG"
    refute grep -q -- '--group' "$UV_LOG" || false
    [[ -x "$HOME/.local/bin/manifest" ]]
}

@test "adds smoke group when smoke.enabled is true" {
    _write_services true false
    _install_playwright_stub
    run uv_sync_home_runtime
    assert_success
    grep -q -- '--group smoke' "$UV_LOG"
    grep -q 'playwright install chromium' "$PLAYWRIGHT_LOG"
}

@test "adds smoke and smoke-agent groups when browser_use.enabled is true" {
    _write_services false true
    run uv_sync_home_runtime
    assert_success
    grep -q -- '--group smoke' "$UV_LOG"
    grep -q -- '--group smoke-agent' "$UV_LOG"
}

@test "deploys manifest wrapper from manifest-cli.sh" {
    run uv_sync_home_runtime
    assert_success
    [[ -f "$HOME/.local/bin/manifest" ]] || return 1 # assertion-safe
    diff -q "$REPO_ROOT/configs/claude/scripts/manifest-cli.sh" "$HOME/.local/bin/manifest"
}

@test "is idempotent across consecutive runs" {
    run uv_sync_home_runtime
    assert_success
    run uv_sync_home_runtime
    assert_success
    assert_equal "$(grep -c '^uv sync' "$UV_LOG" || true)" "2"
    [[ -x "$HOME/.local/bin/manifest" ]] || return 1 # assertion-safe
}

@test "does not deploy wrapper when uv sync fails" {
  cat > "$MOCK_BIN/uv" <<'STUB'
#!/usr/bin/env bash
echo "uv $*" >> "$UV_LOG"
if [[ "$1" == "sync" ]]; then
  exit 1
fi
exit 0
STUB
    chmod +x "$MOCK_BIN/uv"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "uv sync failed"
    [[ ! -f "$HOME/.local/bin/manifest" ]]
}
