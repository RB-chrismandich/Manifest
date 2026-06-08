#!/usr/bin/env bats
# Tests for SkillClaw toggle plumbing in bootstrap/lib/config.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/skillclaw_config.XXXXXX")
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

@test "default skillclaw toggle is disabled (opt-in)" {
    set_bootstrap_defaults
    assert_equal "$ENABLE_SKILLCLAW" "false"
    assert_equal "$SKILLCLAW_SET" "false"
}

@test "--enable-skillclaw sets the toggle" {
    set_bootstrap_defaults
    parse_bootstrap_args --enable-skillclaw
    assert_equal "$ENABLE_SKILLCLAW" "true"
    assert_equal "$SKILLCLAW_SET" "true"
}

@test "write_services_config emits skillclaw section with enabled: false" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false
    export ENABLE_GH=auto ENABLE_GLAB=auto
    run write_services_config
    assert_success
    grep -q "^  skillclaw:" "$SERVICES_CONFIG"
    grep -A4 "^  skillclaw:" "$SERVICES_CONFIG" | grep -q "enabled: false"
}

@test "parse_services_config round-trips skillclaw enabled: true" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=true
    export ENABLE_GH=auto ENABLE_GLAB=auto
    write_services_config
    parse_services_config
    assert_equal "$FILE_SKILLCLAW" "true"
}
