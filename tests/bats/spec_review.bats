#!/usr/bin/env bats
# Tests for configs/claude/scripts/spec_review.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/spec_review.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/spec_review.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "spec_review.sh is executable and prints usage on --help" {
    run bash "$SCRIPT" --help
    assert_success
    assert_output --partial "spec-review"
    assert_output --partial "--silent"
}

@test "spec_review.sh rejects an unknown flag" {
    run bash "$SCRIPT" --bogus
    assert_failure
}

@test "discover_artifacts finds speckit spec/plan/tasks in a specs dir" {
    mkdir -p "$SANDBOX/specs/001-feature"
    : > "$SANDBOX/specs/001-feature/spec.md"
    : > "$SANDBOX/specs/001-feature/plan.md"
    : > "$SANDBOX/specs/001-feature/tasks.md"
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_success
    assert_output --partial "spec	$SANDBOX/specs/001-feature/spec.md"
    assert_output --partial "plan	$SANDBOX/specs/001-feature/plan.md"
    assert_output --partial "tasks	$SANDBOX/specs/001-feature/tasks.md"
}

@test "discover_artifacts finds superpowers design+plan (tasks embedded in plan)" {
    mkdir -p "$SANDBOX/docs/superpowers/specs" "$SANDBOX/docs/superpowers/plans"
    : > "$SANDBOX/docs/superpowers/specs/2026-06-08-thing-design.md"
    : > "$SANDBOX/docs/superpowers/plans/2026-06-08-thing.md"
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_success
    assert_output --partial "spec	$SANDBOX/docs/superpowers/specs/2026-06-08-thing-design.md"
    assert_output --partial "plan	$SANDBOX/docs/superpowers/plans/2026-06-08-thing.md"
    refute_output --partial "tasks	"
}

@test "discover_artifacts prints nothing when no artifacts exist" {
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_output ""
}

@test "assemble_prompt embeds template and role-labelled artifact contents" {
    local tpl="$SANDBOX/tpl.md"; printf 'HEAD
{{ARTIFACTS}}
TAIL
' > "$tpl"
    printf 'spec body here
' > "$SANDBOX/spec.md"
    printf 'plan body here
' > "$SANDBOX/plan.md"
    source "$SCRIPT"
    run assemble_prompt "$tpl" "spec	$SANDBOX/spec.md" "plan	$SANDBOX/plan.md"
    assert_success
    assert_output --partial "HEAD"
    assert_output --partial "=== SPEC: $SANDBOX/spec.md ==="
    assert_output --partial "spec body here"
    assert_output --partial "=== PLAN: $SANDBOX/plan.md ==="
    assert_output --partial "plan body here"
    refute_output --partial "{{ARTIFACTS}}"
}
