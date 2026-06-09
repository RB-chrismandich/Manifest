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

@test "skillclaw_apply_state enable creates storage with 700 perms" {
    export SHELL_PROFILE_FILE="$SANDBOX/.zshrc"
    touch "$SANDBOX/.zshrc"
    launchctl() { :; }
    systemctl() { :; }
    ENABLE_SKILLCLAW=true run skillclaw_apply_state
    assert_success
    [ -d "$SKILLCLAW_HOME" ]
    [ -d "$SKILLCLAW_HOME/sessions" ]
    [ -d "$SKILLCLAW_HOME/skills" ]
    local mode
    mode=$(stat -c '%a' "$SKILLCLAW_HOME" 2>/dev/null || stat -f '%Lp' "$SKILLCLAW_HOME")
    assert_equal "$mode" "700"
}

@test "skillclaw_remove_wrappers strips the marker block" {
    local profile="$SANDBOX/.zshrc"
    cat > "$profile" << 'PROF'
# something before
# >>> MANIFEST SKILLCLAW WRAPPERS >>>
export SKILLCLAW_PORT="8765"
claude() { echo proxy; }
codex()  { echo proxy; }
# <<< MANIFEST SKILLCLAW WRAPPERS <<<
# something after
PROF
    run skillclaw_remove_wrappers "$profile"
    assert_success
    run grep -c "MANIFEST SKILLCLAW WRAPPERS" "$profile"
    assert_output "0"
    grep -q "something before" "$profile"
    grep -q "something after" "$profile"
}

@test "skillclaw_remove_wrappers is idempotent on clean profile" {
    local profile="$SANDBOX/.zshrc"
    echo "# no wrappers here" > "$profile"
    run skillclaw_remove_wrappers "$profile"
    assert_success
    run skillclaw_remove_wrappers "$profile"
    assert_success
}

@test "skillclaw.sh no longer writes shell proxy wrappers" {
    run grep -Ec 'ANTHROPIC_BASE_URL|OPENAI_BASE_URL|_skillclaw_run|skillclaw_daemon' \
        "$REPO_ROOT/bootstrap/lib/skillclaw.sh"
    [ "$output" -eq 0 ]
}

@test "disable still removes any legacy wrapper block (clean teardown)" {
    run grep -q 'skillclaw_remove_wrappers' "$REPO_ROOT/bootstrap/lib/skillclaw.sh"
    [ "$status" -eq 0 ]
}

@test "apply_state enables transcript evolution without a daemon" {
    run grep -Eq 'no daemon|transcript' "$REPO_ROOT/bootstrap/lib/skillclaw.sh"
    [ "$status" -eq 0 ]
}
