#!/usr/bin/env bats
# CDDL scripted orchestrator retired — cddl_loop.py is a deprecation stub only.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CDDL="$REPO_ROOT/configs/claude/scripts/cddl_loop.py"

@test "cddl_loop --help exits 0 with retirement notice" {
    run python3 "$CDDL" --help
    assert_success
    assert_output --partial "/spec-implement-loop"
}

@test "cddl_loop start exits 2 with retirement notice" {
    run python3 "$CDDL" start specs/001-fx 2>&1
    assert_failure 2
    assert_output --partial "/spec-implement-loop"
}
