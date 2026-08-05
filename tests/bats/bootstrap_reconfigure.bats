#!/usr/bin/env bats
# Tests for bootstrap.sh run_reconfigure wiring. Also covers
# warn_stale_disabled_configs (#549), which must fire on
# --reconfigure, not only from print_summary in the main() install path.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/bootstrap_reconfigure.XXXXXX")

    # Real gates under test come from common.sh and deploy.sh
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # bootstrap.sh executes main on load, so extract run_reconfigure instead
    awk '/^run_reconfigure\(\) \{/,/^\}/' "$REPO_ROOT/bootstrap.sh" > "$SANDBOX/run_reconfigure.sh"
    # shellcheck disable=SC1090
    source "$SANDBOX/run_reconfigure.sh"

    # Stub every reconfigure collaborator.
    print_header() { :; }
    print_success() { :; }
    print_info() { :; }
    print_warning() { :; }
    print_error() { :; }
    load_existing_config() { :; }
    run_bootstrap_hook() { :; }
    prompt_yes_no() { return 0; }
    setup_manifest_state_dirs() { :; }
    configure_shell_profile_state() { :; }
    write_services_config() { :; }
    skillclaw_apply_state() { :; }
    install_mcp_servers() { :; }
    check_uv() { :; }
    uv_sync_home_runtime() { :; }

    export TARGET_DIR="$SANDBOX/home/.claude"
    mkdir -p "$TARGET_DIR"
    export SERVICES_CONFIG="$TARGET_DIR/config/services.yml"
    export INSTALL_MCP=false
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export GEMINI_TARGET_DIR="$SANDBOX/home/.gemini"
    export CODEX_TARGET_DIR="$SANDBOX/home/.codex"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false ENABLE_BROWSER_USE=false
    export BOLD='' NC=''
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "reconfigure with --disable-claude warns about the stale deployed CLAUDE.md (#549)" {
    # Un-stub print_warning so the real warn_stale_disabled_configs output is
    # observable; every other collaborator stays stubbed from setup().
    print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
    echo "deployed guide" > "$TARGET_DIR/CLAUDE.md"
    export ENABLE_CLAUDE=false

    run run_reconfigure
    assert_success
    assert_output --partial "claude"
    assert_output --partial "$TARGET_DIR/CLAUDE.md"
}

@test "reconfigure with claude still enabled does not warn about CLAUDE.md" {
    print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
    echo "deployed guide" > "$TARGET_DIR/CLAUDE.md"
    export ENABLE_CLAUDE=true

    run run_reconfigure
    assert_success
    refute_output --partial "claude disabled"
}
