#!/usr/bin/env bats
# Tests for bootstrap/lib/skillclaw.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/skillclaw_lib.XXXXXX")
    export SKILLCLAW_HOME="$SANDBOX/.skillclaw"
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { echo "ERR: $*"; }
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/skillclaw.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "skillclaw_init_storage creates dirs with 700 perms" {
    run skillclaw_init_storage
    assert_success
    [ -d "$SKILLCLAW_HOME" ]
    [ -d "$SKILLCLAW_HOME/sessions" ]
    [ -d "$SKILLCLAW_HOME/skills" ]
    local mode
    mode=$(stat -f '%Lp' "$SKILLCLAW_HOME" 2>/dev/null || stat -c '%a' "$SKILLCLAW_HOME")
    assert_equal "$mode" "700"
}
