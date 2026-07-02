#!/usr/bin/env bats
# Tests for tests/lint/check_bats_assertions.sh — the guard against
# silently-passing non-final bare [[ ]] assertions (issue #479).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

CHECKER="$BATS_TEST_DIRNAME/../lint/check_bats_assertions.sh"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/bats_assert_lint.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "planted non-final bare [[ ]] violation is caught" {
    printf '@test "t" {\n    out="x"\n    [[ "$out" == "y" ]]\n    echo after\n}\n' \
        > "$SANDBOX/bad.bats"
    run "$CHECKER" "$SANDBOX/bad.bats"
    assert_failure
    assert_output --partial "bad.bats:3"
}

@test "chained || return 1 assertion passes" {
    printf '@test "t" {\n    out="x"\n    [[ "$out" == "x" ]] || return 1\n    echo after\n}\n' \
        > "$SANDBOX/good.bats"
    run "$CHECKER" "$SANDBOX/good.bats"
    assert_success
}

@test "final-position bare [[ ]] passes (bats catches it there)" {
    printf '@test "t" {\n    out="x"\n    [[ "$out" == "x" ]]\n}\n' \
        > "$SANDBOX/final.bats"
    run "$CHECKER" "$SANDBOX/final.bats"
    assert_success
}

@test "if-condition [[ ]] is not an assertion and passes" {
    printf '@test "t" {\n    if [[ -f /etc/hosts ]]; then\n        echo yes\n    fi\n    echo after\n}\n' \
        > "$SANDBOX/cond.bats"
    run "$CHECKER" "$SANDBOX/cond.bats"
    assert_success
}

@test "inline assertion-safe opt-out passes" {
    printf '@test "t" {\n    [[ -n "$PATH" ]] # assertion-safe\n    echo after\n}\n' \
        > "$SANDBOX/optout.bats"
    run "$CHECKER" "$SANDBOX/optout.bats"
    assert_success
}

@test "no-args mode scans tracked .bats and exits 0 at HEAD" {
    run "$CHECKER"
    assert_success
}
