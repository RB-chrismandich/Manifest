#!/usr/bin/env bats
# Tests for browser-use toggle plumbing in bootstrap/lib/config.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/browser_use_config.XXXXXX")
    export SERVICES_CONFIG="$SANDBOX/config/services.yml"
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/config.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "default browser_use toggle is disabled" {
    set_bootstrap_defaults
    assert_equal "$ENABLE_BROWSER_USE" "false"
    assert_equal "$BROWSER_USE_SET" "false"
}

@test "--enable-browser-use sets the toggle" {
    set_bootstrap_defaults
    parse_bootstrap_args --enable-browser-use
    assert_equal "$ENABLE_BROWSER_USE" "true"
    assert_equal "$BROWSER_USE_SET" "true"
}

@test "--disable-browser-use sets the toggle off explicitly" {
    set_bootstrap_defaults
    parse_bootstrap_args --disable-browser-use
    assert_equal "$ENABLE_BROWSER_USE" "false"
    assert_equal "$BROWSER_USE_SET" "true"
}

@test "write_services_config emits browser_use section with enabled: false" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false ENABLE_BROWSER_USE=false
    export ENABLE_GH=auto ENABLE_GLAB=auto
    run write_services_config
    assert_success
    grep -q "^  browser_use:" "$SERVICES_CONFIG"
    grep -A4 "^  browser_use:" "$SERVICES_CONFIG" | grep -q "enabled: false"
}

@test "write_services_config emits browser_use section with enabled: true" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false ENABLE_BROWSER_USE=true
    export ENABLE_GH=auto ENABLE_GLAB=auto
    run write_services_config
    assert_success
    grep -q "^  browser_use:" "$SERVICES_CONFIG"
    grep -A4 "^  browser_use:" "$SERVICES_CONFIG" | grep -q "enabled: true"
}

@test "parse_services_config round-trips browser_use enabled: true" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false ENABLE_BROWSER_USE=true
    export ENABLE_GH=auto ENABLE_GLAB=auto
    write_services_config
    parse_services_config
    assert_equal "$FILE_BROWSER_USE" "true"
}

@test "parse_services_config round-trips browser_use enabled: false" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false ENABLE_BROWSER_USE=false
    export ENABLE_GH=auto ENABLE_GLAB=auto
    write_services_config
    parse_services_config
    assert_equal "$FILE_BROWSER_USE" "false"
}
