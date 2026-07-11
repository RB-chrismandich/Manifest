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
    # Tier-1 honeypot: root AND subdirs must be 700 (session data may be unscrubbed).
    local d
    for d in "$SKILLCLAW_HOME" "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"; do
        local mode
        mode=$(stat -c '%a' "$d" 2>/dev/null || stat -f '%Lp' "$d")
        assert_equal "$mode" "700"
    done
}

@test "skillclaw_apply_state re-enforces 700 on already-existing dirs that drifted looser" {
    # docs/SKILLCLAW.md: "set at enable time and re-enforced on each
    # skillclaw_apply_state call" — simulate a second enable run after
    # something loosened the perms (e.g. a manual chmod, an unrelated tool).
    export SHELL_PROFILE_FILE="$SANDBOX/.zshrc"
    touch "$SANDBOX/.zshrc"
    launchctl() { :; }
    systemctl() { :; }
    mkdir -p "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
    chmod 755 "$SKILLCLAW_HOME" "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
    ENABLE_SKILLCLAW=true run skillclaw_apply_state
    assert_success
    local d
    for d in "$SKILLCLAW_HOME" "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"; do
        local mode
        mode=$(stat -c '%a' "$d" 2>/dev/null || stat -f '%Lp' "$d")
        assert_equal "$mode" "700"
    done
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
    local profile="$SANDBOX/.zshrc"
    export SHELL_PROFILE_FILE="$profile"
    cat > "$profile" << 'PROF'
# keep me
# >>> MANIFEST SKILLCLAW WRAPPERS >>>
claude() { echo proxy; }
# <<< MANIFEST SKILLCLAW WRAPPERS <<<
PROF
    launchctl() { :; }
    systemctl() { :; }
    ENABLE_SKILLCLAW=false run skillclaw_apply_state
    assert_success
    run grep -c "MANIFEST SKILLCLAW WRAPPERS" "$profile"
    assert_output "0"
    grep -q "keep me" "$profile"
}

@test "apply_state enables transcript evolution without a daemon" {
    run grep -Eq 'no daemon|transcript' "$REPO_ROOT/bootstrap/lib/skillclaw.sh"
    [ "$status" -eq 0 ]
}

@test "skillclaw_apply_state survives set -e when no launchd plist exists" {
    # _skillclaw_remove_launchd ended with `[[ -f plist ]] && {...}` — when the
    # plist is absent (the normal case) that list returns 1 as the function's
    # exit status, and under bootstrap.sh's `set -e` the bare call aborted the
    # ENTIRE bootstrap silently right after deploy_configs (found 2026-06-11:
    # every run died before skillclaw state, python deps, auth, and summary).
    run bash -c "
        set -e
        HOME='$SANDBOX/home'
        mkdir -p \"\$HOME\"
        export SKILLCLAW_HOME='$SANDBOX/.skillclaw'
        export SHELL_PROFILE_FILE='$SANDBOX/home/.zshrc'
        touch '$SANDBOX/home/.zshrc'
        print_step() { :; }; print_success() { :; }; print_info() { :; }
        print_warning() { :; }; print_error() { :; }
        launchctl() { :; }; systemctl() { :; }
        source '$REPO_ROOT/bootstrap/lib/skillclaw.sh'
        ENABLE_SKILLCLAW=true skillclaw_apply_state
        echo SURVIVED
    "
    assert_success
    assert_output --partial "SURVIVED"
}
