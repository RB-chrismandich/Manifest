#!/usr/bin/env bats
# Tests for bootstrap/lib/config.sh write_services_config

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/bootstrap_services.XXXXXX")
    export SERVICES_CONFIG="$SANDBOX/config/services.yml"

    # Stub print helpers (defined in common.sh; config.sh calls them)
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

@test "write_services_config emits antigravity section with enabled: false" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=false ENABLE_SKILLCLAW=false
    export ENABLE_GH=auto ENABLE_GLAB=auto

    run write_services_config
    assert_success

    grep -q "^  antigravity:" "$SERVICES_CONFIG"
    grep -A5 "^  antigravity:" "$SERVICES_CONFIG" | grep -q "enabled: false"
}

@test "write_services_config emits antigravity section with enabled: true" {
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true
    export ENABLE_ANTIGRAVITY=true ENABLE_SKILLCLAW=false
    export ENABLE_GH=auto ENABLE_GLAB=auto

    run write_services_config
    assert_success

    grep -q "^  antigravity:" "$SERVICES_CONFIG"
    grep -A5 "^  antigravity:" "$SERVICES_CONFIG" | grep -q "enabled: true"
}
