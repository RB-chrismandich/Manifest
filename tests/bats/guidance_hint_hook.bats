#!/usr/bin/env bats
# T017 — guidance_hint.py fires a one-shot hint at a recognized Workflow Moment
# and stays silent on unrelated actions (spec 362, US2; SC-003 mechanism).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
HINT="$REPO_ROOT/configs/claude/scripts/guidance_hint.py"

setup() {
    # Isolated agent home so rate-limit state never leaks between tests/runs.
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/guidance_hint.XXXXXX")
    export HOME="$SANDBOX"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Simulate a Claude Code PreToolUse Bash payload on stdin.
payload() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1"; }

@test "git commit surfaces a commit-guidance hint" {
    run bash -c "echo '$(payload "git commit -m wip")' | '$HINT'"
    assert_success
    assert_output --partial "/project-verify"
}

@test "gh pr create surfaces a PR-open hint" {
    run bash -c "echo '$(payload "gh pr create --fill")' | '$HINT'"
    assert_success
    assert_output --partial "/"
}

@test "an unrelated command produces no hint (silent, exit 0)" {
    run bash -c "echo '$(payload "ls -la")' | '$HINT'"
    assert_success
    assert_output ""
}

@test "explicit --moment emits that moment's hint" {
    run "$HINT" --moment pre-commit
    assert_success
    assert_output --partial "/project-verify"
}

@test "fails open: malformed payload exits 0 with no output" {
    run bash -c "echo 'not json' | '$HINT'"
    assert_success
    assert_output ""
}

@test "--help works before any dependency load" {
    run "$HINT" --help
    assert_success
    assert_output --partial "usage:"
}
