#!/usr/bin/env bats
# Tests for the --mode product|technical flag on spec_review.sh (feature 365, T036/T037).
# Contract: specs/365-lifecycle-codification/contracts/verify-and-specreview.md

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/spec_review.sh"

# The script guards `main` behind a BASH_SOURCE check, so sourcing loads parse_args without running.
load_script() { source "$SCRIPT"; }

@test "--help exits 0 and lists --mode" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]; [[ "$output" == *"--mode"* ]]
}
@test "--help succeeds in a clean env (no deps required before help)" {
    run env -i PATH="$PATH" bash "$SCRIPT" --help
    [ "$status" -eq 0 ]; [[ "$output" == *"--mode"* ]]
}
@test "default (no --mode) leaves the state dir unchanged" {
    load_script
    parse_args
    [ "$SPEC_REVIEW_STATE" = ".spec-review" ]
    [ -z "$MODE" ]
}
@test "--mode product routes the state dir to .spec-review/product" {
    load_script
    parse_args --mode product
    [ "$SPEC_REVIEW_STATE" = ".spec-review/product" ]
    [ "$MODE" = "product" ]
}
@test "--mode technical routes the state dir to .spec-review/technical" {
    load_script
    parse_args --mode technical
    [ "$SPEC_REVIEW_STATE" = ".spec-review/technical" ]
    [ "$MODE" = "technical" ]
}
@test "invalid --mode -> exit 2 with a curated error" {
    load_script
    run parse_args --mode bogus
    [ "$status" -eq 2 ]; [[ "$output" == *"invalid --mode"* ]]
}
@test "--mode composes with explicit artifact flags (default behavior preserved)" {
    load_script
    parse_args --mode product --spec ./spec.md --plan ./plan.md --tasks ./tasks.md
    [ "$SPEC" = "./spec.md" ]; [ "$PLAN" = "./plan.md" ]; [ "$TASKS" = "./tasks.md" ]
    [ "$SPEC_REVIEW_STATE" = ".spec-review/product" ]
}

@test "--mode technical selects the technical template (it must exist)" {
    # The [[ -f ]] guard silently fell back to the generic template while
    # prompts/spec_review_technical.md did not exist — phases 3 and 7 ran
    # byte-identical reviews (issue #463).
    [ -f "$BATS_TEST_DIRNAME/../../configs/claude/prompts/spec_review_technical.md" ]
    # shellcheck disable=SC1090
    source "$SCRIPT"
    parse_args --mode technical
    [[ "$SPEC_REVIEW_TEMPLATE" == *"spec_review_technical.md" ]]
}

@test "technical template keeps the shared output contract (NO_ISSUES token)" {
    grep -q 'NO_ISSUES' "$BATS_TEST_DIRNAME/../../configs/claude/prompts/spec_review_technical.md"
    grep -q '{{ARTIFACTS}}' "$BATS_TEST_DIRNAME/../../configs/claude/prompts/spec_review_technical.md"
}
