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
    export MANIFEST_STATE_ROOT="$HOME/.manifest"
    export SHELL_PROFILE_FILE="$HOME/.zshrc"
    mkdir -p "$TARGET_DIR/config" "$HOME/.local/bin"
    : > "$SHELL_PROFILE_FILE"
    # deploy_configs always lands both before this function runs; without them
    # `uv sync --project` has no project to sync, which the function now refuses.
    : > "$TARGET_DIR/pyproject.toml"
    : > "$TARGET_DIR/uv.lock"

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
    # A real venv always has a working interpreter; without one the health check
    # would (correctly) treat this stub tree as a venv to rebuild.
    ln -sf "$(command -v python3)" "$TARGET_DIR/.venv/bin/python3"
}

# A venv that looks installed and runs, so heal_broken_home_venv leaves it alone.
_install_healthy_venv_stub() {
    mkdir -p "$TARGET_DIR/.venv/bin"
    ln -sf "$(command -v python3)" "$TARGET_DIR/.venv/bin/python3"
    printf '#!/bin/sh\nexit 0\n' > "$TARGET_DIR/.venv/bin/manifest"
    chmod +x "$TARGET_DIR/.venv/bin/manifest"
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

@test "browser_use implies smoke exactly once and installs the browser" {
    # browser-use layers on the smoke group but used to leave install_playwright
    # false, so a browser-use-only install had the driver and no browser.
    _write_services false true
    _install_playwright_stub
    run uv_sync_home_runtime
    assert_success
    assert_equal "$(grep -c -- '--group smoke ' "$UV_LOG" || true)" "1"
    grep -q -- '--group smoke-agent' "$UV_LOG"
    grep -q 'playwright install chromium' "$PLAYWRIGHT_LOG"
    grep -q '^groups=core,smoke,smoke-agent$' "$MANIFEST_STATE_ROOT/runtime.env"
}

@test "refuses to sync when the deploy left no pyproject.toml" {
    rm -f "$TARGET_DIR/pyproject.toml"
    run uv_sync_home_runtime
    assert_success # fail-open: one broken runtime must not abort the bootstrap
    assert_output --partial "pyproject.toml is missing"
    [[ ! -e "$UV_LOG" ]] || [[ ! -s "$UV_LOG" ]] || return 1 # no sync attempted
    [[ ! -f "$HOME/.local/bin/manifest" ]]
}

@test "refuses to sync when the deploy left no uv.lock" {
    rm -f "$TARGET_DIR/uv.lock"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "uv.lock is missing"
}

@test "warns instead of silently skipping groups when services.yml is absent" {
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "not found"
    assert_output --partial "core runtime only"
}

@test "reports an unparseable services.yml and reuses the last known groups" {
    # A probe failure used to be indistinguishable from "service disabled", which
    # silently downgraded an enabled service to a core-only install.
    printf 'services: {broken\n' > "$TARGET_DIR/config/services.yml"
    mkdir -p "$MANIFEST_STATE_ROOT"
    echo "groups=core,smoke" > "$MANIFEST_STATE_ROOT/runtime.env"
    _install_playwright_stub
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "Could not read"
    assert_output --partial "Reusing the previous sync's groups"
    grep -q -- '--group smoke' "$UV_LOG"
}

@test "treats a non-mapping services.yml as unresolved rather than disabled" {
    printf -- '- not\n- a mapping\n' > "$TARGET_DIR/config/services.yml"
    run uv_sync_home_runtime
    assert_success
    refute_output --partial "Reusing the previous sync's groups"
    grep -q '^uv sync' "$UV_LOG"
}

@test "recreates a venv whose interpreter no longer runs" {
    mkdir -p "$TARGET_DIR/.venv/bin"
    ln -sf "$SANDBOX/gone/python3" "$TARGET_DIR/.venv/bin/python3"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "recreating"
    [[ ! -d "$TARGET_DIR/.venv" ]] # removed so uv rebuilds it from the lockfile
}

@test "leaves a healthy venv in place" {
    _install_healthy_venv_stub
    run uv_sync_home_runtime
    assert_success
    refute_output --partial "recreating"
    [[ -x "$TARGET_DIR/.venv/bin/manifest" ]] || return 1 # assertion-safe
}

@test "never writes through a symlink at ~/.local/bin/manifest" {
    echo "victim content" > "$SANDBOX/victim"
    ln -sf "$SANDBOX/victim" "$HOME/.local/bin/manifest"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "Replacing symlink"
    assert_equal "$(cat "$SANDBOX/victim")" "victim content"
    [[ ! -L "$HOME/.local/bin/manifest" ]] || return 1 # assertion-safe
    diff -q "$REPO_ROOT/configs/claude/scripts/manifest-cli.sh" "$HOME/.local/bin/manifest"
}

@test "backs up a foreign manifest binary instead of clobbering it" {
    printf '#!/bin/sh\necho some other project\n' > "$HOME/.local/bin/manifest"
    chmod +x "$HOME/.local/bin/manifest"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "was not installed by Manifest"
    grep -q 'some other project' "$HOME/.local/bin/manifest.pre-manifest.bak"
    diff -q "$REPO_ROOT/configs/claude/scripts/manifest-cli.sh" "$HOME/.local/bin/manifest"
}

@test "keeps an existing backup rather than overwriting it" {
    printf 'first foreign\n' > "$HOME/.local/bin/manifest.pre-manifest.bak"
    printf 'second foreign\n' > "$HOME/.local/bin/manifest"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "existing backup kept"
    grep -q 'first foreign' "$HOME/.local/bin/manifest.pre-manifest.bak"
}

@test "refuses when the destination is a directory and keeps bootstrapping" {
    mkdir -p "$HOME/.local/bin/manifest"
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "is a directory"
    [[ -d "$HOME/.local/bin/manifest" ]] || return 1 # assertion-safe
}

@test "reports an already-current wrapper instead of rewriting it" {
    run uv_sync_home_runtime
    assert_success
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "already current"
}

@test "heals a lost executable bit on an already-current wrapper" {
    run uv_sync_home_runtime
    assert_success
    chmod -x "$HOME/.local/bin/manifest"
    run uv_sync_home_runtime
    assert_success
    [[ -x "$HOME/.local/bin/manifest" ]] || return 1 # assertion-safe
}

@test "replaces a stale wrapper copy" {
    printf '#!/usr/bin/env bash\n# manifest-cli-wrapper\nexit 7\n' > "$HOME/.local/bin/manifest"
    chmod +x "$HOME/.local/bin/manifest"
    run uv_sync_home_runtime
    assert_success
    refute_output --partial "was not installed by Manifest"
    diff -q "$REPO_ROOT/configs/claude/scripts/manifest-cli.sh" "$HOME/.local/bin/manifest"
}

@test "leaves no temp file behind on a successful install" {
    run uv_sync_home_runtime
    assert_success
    run bash -c 'ls "$HOME"/.local/bin/manifest.tmp.* 2>/dev/null | wc -l | tr -d " "'
    assert_output "0"
}

@test "clears temp files left by an interrupted install" {
    printf 'half-written\n' > "$HOME/.local/bin/manifest.tmp.99999"
    run uv_sync_home_runtime
    assert_success
    run bash -c 'ls "$HOME"/.local/bin/manifest.tmp.* 2>/dev/null | wc -l | tr -d " "'
    assert_output "0"
}

@test "records the clone path and groups in the runtime stamp" {
    _write_services true false
    _install_playwright_stub
    run uv_sync_home_runtime
    assert_success
    grep -q "^clone_path=$REPO_ROOT$" "$MANIFEST_STATE_ROOT/runtime.env"
    grep -q "^runtime_root=$TARGET_DIR$" "$MANIFEST_STATE_ROOT/runtime.env"
    grep -q '^groups=core,smoke$' "$MANIFEST_STATE_ROOT/runtime.env"
}

@test "skips the browser install when the smoke group did not land" {
    _write_services true false
    run uv_sync_home_runtime
    assert_success
    assert_output --partial "playwright is missing"
    [[ ! -s "$PLAYWRIGHT_LOG" ]]
}

@test "adds ~/.local/bin to the shell profile exactly once" {
    run uv_sync_home_runtime
    assert_success
    run uv_sync_home_runtime
    assert_success
    assert_equal "$(grep -c '\.local/bin' "$SHELL_PROFILE_FILE" || true)" "1"
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
