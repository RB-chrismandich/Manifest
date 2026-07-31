#!/usr/bin/env bats
# T4.2 (spec 674) — the per-bundle cutover tool's REFUSALS.
#
# Everything asserted here is a precondition that must stop the run before a
# single directory is deleted. The tool's whole value is that it fails closed:
# once ~/.claude/skills is emptied for a bundle whose plugin did not install,
# the user has no skills from that bundle and no error explaining why.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/cutover_bundle.sh"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/cutover_bundle.XXXXXX")"
    export MANIFEST_STATE_DIR="$SANDBOX/state"
    export MANIFEST_SKILLS_DIR="$SANDBOX/harness"
    export MANIFEST_SKILL_REGISTRY="$SANDBOX/skill_policies.yml"
    mkdir -p "$MANIFEST_STATE_DIR" "$MANIFEST_SKILLS_DIR"
    printf 'expected_total: 2\nbundles:\n  manifest-docs:  # 2 skills\n    - alpha\n    - beta\n' \
        > "$MANIFEST_SKILL_REGISTRY"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "--help exits 0 and is at most 15 lines" {
    run "$SCRIPT" --help
    assert_success
    [ "${#lines[@]}" -le 15 ]
}

@test "a missing bundle name is refused" {
    run "$SCRIPT"
    assert_failure
    assert_output --partial "bundle name is required"
}

@test "refuses when no Phase 0 snapshot exists" {
    # The tarball is the ONLY rollback that survives Phase 5 -- every rollback
    # the input designs proposed calls a script this cutover retires.
    run "$SCRIPT" manifest-docs --allow-unverified-devin
    assert_failure
    assert_output --partial "no Phase 0 snapshot"
}

@test "refuses while Devin's inheritance is unverified" {
    # Emptying ~/.claude/skills is what breaks Devin's read_config_from.claude
    # path. Phase 2 froze that tree but left it populated, so Devin was safe
    # until this step.
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    run env -u ALLOW "$SCRIPT" manifest-docs
    assert_failure
    assert_output --partial "Devin"
}

@test "the Devin refusal names both remedies" {
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    run "$SCRIPT" manifest-docs
    assert_output --partial "devin auth login"
    assert_output --partial "--allow-unverified-devin"
}

@test "refuses a bundle that owns no skills in the registry" {
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    run "$SCRIPT" not-a-bundle --allow-unverified-devin
    assert_failure
}

@test "does not use .deployed-skills anywhere" {
    # Measured wrong on a live machine; two designs keyed the retire step on it
    # and would have left a live copy double-loading against its plugin twin.
    # It appears once, in the PRESERVE allowlist -- a name that must survive the
    # delete, not a source that is read. What must be absent is any READ of it.
    run bash -c "grep -vE '^[[:space:]]*#' '$SCRIPT' | grep 'deployed-skills' | grep -cE 'read|cat|<|while' || true"
    assert_output "0"
}

@test "does not use skillOverrides" {
    # `off` makes the bare name a hard Unknown command, uninstall does not clear
    # the override, and the write target is the file whose RMW race already lost
    # this user's `model` key.
    # Comments stripped: the header NAMES skillOverrides to explain why it is
    # avoided, so grepping raw source tests the prose, not the behaviour.
    run bash -c "grep -vE '^[[:space:]]*#' '$SCRIPT' | grep -c 'skillOverride' || true"
    assert_output "0"
}
