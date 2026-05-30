#!/usr/bin/env bats
# Tests for bootstrap/lib/common.sh deploy_home_skills + deploy.sh skills wiring

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_skills.XXXXXX")
    # Source the helpers under test
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "deploy_home_skills copies real directories from physical source" {
    mkdir -p "$SANDBOX/src/demo-skill"
    echo "body" > "$SANDBOX/src/demo-skill/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/demo-skill" ]
    [ ! -L "$SANDBOX/dest" ]
    assert_equal "$(cat "$SANDBOX/dest/demo-skill/SKILL.md")" "body"
}

@test "deploy_home_skills prunes skills removed from source" {
    mkdir -p "$SANDBOX/src/keep" "$SANDBOX/dest/stale"
    echo k > "$SANDBOX/src/keep/SKILL.md"
    echo s > "$SANDBOX/dest/stale/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/keep" ]
    [ ! -e "$SANDBOX/dest/stale" ]
}

@test "deploy_home_skills fails clearly when source missing" {
    run deploy_home_skills "$SANDBOX/nonexistent" "$SANDBOX/dest"
    assert_failure
    assert_output --partial "not found"
}
