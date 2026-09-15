#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/../.."
    source "$SCRIPT_DIR/bootstrap/lib/common.sh"
    source "$SCRIPT_DIR/bootstrap/lib/config.sh"
    source "$SCRIPT_DIR/bootstrap/lib/jules.sh"
    set_bootstrap_defaults
}

@test "Jules installation defaults disabled without invoking npm" {
    npm() { return 99; }
    command_exists() { return 1; }
    run check_jules
    assert_success
}

@test "explicit Jules flag wins over existing enabled service" {
    SERVICES_CONFIG="$BATS_TEST_TMPDIR/services.yml"
    printf 'services:\n  jules:\n    enabled: true\n' > "$SERVICES_CONFIG"
    parse_bootstrap_args --disable-jules
    load_existing_config
    assert_equal "$ENABLE_JULES" false
}

@test "existing Jules service is loaded when flag absent" {
    SERVICES_CONFIG="$BATS_TEST_TMPDIR/services.yml"
    printf 'services:\n  jules:\n    enabled: true\n' > "$SERVICES_CONFIG"
    load_existing_config
    assert_equal "$ENABLE_JULES" true
}

@test "Jules install failure reaches the bootstrap caller" {
    ENABLE_JULES=true
    command_exists() { [[ "$1" == npm ]]; }
    prompt_yes_no() { return 0; }
    npm() { return 42; }
    run check_jules
    assert_failure
}

@test "successful auth probe preserves login without opening browser" {
    ENABLE_JULES=true
    command_exists() { return 0; }
    python3() { return 0; }
    jules() { return 99; }
    run check_jules_auth
    assert_success
    assert_output --partial "authenticated"
}

@test "noninteractive failed auth probe does not silently pass" {
    ENABLE_JULES=true
    command_exists() { return 0; }
    python3() { return 1; }
    run check_jules_auth
    assert_failure
    assert_output --partial "jules login"
}
