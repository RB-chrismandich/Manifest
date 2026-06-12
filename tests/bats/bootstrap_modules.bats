#!/usr/bin/env bats
# Tests for bootstrap/lib/modules.sh — the hook registry powering the
# bootstrap extension system (issue #329: previously zero coverage).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

MODULES_LIB="$BATS_TEST_DIRNAME/../../bootstrap/lib/modules.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/modules_test.XXXXXX")
}

teardown() {
    rm -rf "$TEST_DIR"
}

# Source the lib with stubbed print helpers inside a fresh bash so each test
# gets clean hook arrays.
run_in_harness() {
    bash -c "
        set -u
        print_step()    { echo \"STEP: \$1\"; }
        print_info()    { echo \"INFO: \$1\"; }
        print_success() { echo \"SUCCESS: \$1\"; }
        print_warning() { echo \"WARNING: \$1\"; }
        SCRIPT_DIR='$TEST_DIR'
        source '$MODULES_LIB'
        $1
    "
}

@test "register and run a hook function" {
    run run_in_harness '
        my_hook() { echo "my_hook ran"; }
        register_bootstrap_hook after_deploy my_hook
        run_bootstrap_hook after_deploy
    '
    assert_success
    assert_output --partial "my_hook ran"
}

@test "running an empty hook is a no-op under set -u (Bash 3.2 guard)" {
    run run_in_harness 'run_bootstrap_hook after_verify; echo "survived"'
    assert_success
    assert_output --partial "survived"
}

@test "registering against an unknown hook warns and returns 1" {
    run run_in_harness '
        register_bootstrap_hook not_a_hook some_func || echo "rejected"
    '
    assert_success
    assert_output --partial "Unknown bootstrap hook"
    assert_output --partial "rejected"
}

@test "running an unknown hook warns and returns 1" {
    run run_in_harness '
        run_bootstrap_hook not_a_hook || echo "rejected"
    '
    assert_success
    assert_output --partial "unknown bootstrap hook"
    assert_output --partial "rejected"
}

@test "a registered-but-undefined function warns instead of crashing" {
    run run_in_harness '
        register_bootstrap_hook after_auth ghost_func
        run_bootstrap_hook after_auth
        echo "survived"
    '
    assert_success
    assert_output --partial "Registered hook function not found: ghost_func"
    assert_output --partial "survived"
}

@test "multiple hooks on the same lifecycle point run in registration order" {
    run run_in_harness '
        first()  { echo "first ran"; }
        second() { echo "second ran"; }
        register_bootstrap_hook before_install first
        register_bootstrap_hook before_install second
        run_bootstrap_hook before_install
    '
    assert_success
    first_line=$(echo "$output" | grep -n "first ran" | cut -d: -f1)
    second_line=$(echo "$output" | grep -n "second ran" | cut -d: -f1)
    [ "$first_line" -lt "$second_line" ]
}

@test "load_bootstrap_modules sources every .sh module and counts them" {
    mkdir -p "$TEST_DIR/bootstrap/modules"
    cat > "$TEST_DIR/bootstrap/modules/a_mod.sh" << 'EOF'
a_hook() { echo "module a hook"; }
register_bootstrap_hook after_deploy a_hook
EOF
    cat > "$TEST_DIR/bootstrap/modules/b_mod.sh" << 'EOF'
echo "module b sourced"
EOF
    run run_in_harness '
        load_bootstrap_modules
        run_bootstrap_hook after_deploy
    '
    assert_success
    assert_output --partial "Loaded bootstrap module: a_mod.sh"
    assert_output --partial "module b sourced"
    assert_output --partial "Bootstrap modules loaded: 2"
    assert_output --partial "module a hook"
}

@test "load_bootstrap_modules is a no-op when the module dir is absent" {
    run run_in_harness '
        BOOTSTRAP_MODULE_DIR="$SCRIPT_DIR/does-not-exist" load_bootstrap_modules
        echo "survived"
    '
    assert_success
    assert_output --partial "survived"
}
