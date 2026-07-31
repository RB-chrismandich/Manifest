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
    # Never the real ~/.config/devin/skills: the gate CREATES this path, and an
    # earlier version of these tests left a dangling link on the live machine.
    export DEVIN_SKILLS_LINK="$SANDBOX/devin/skills"
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

@test "refuses when Devin cannot see the harness tree" {
    # Emptying ~/.claude/skills is what breaks Devin's read_config_from.claude
    # path. The gate checks INHERITANCE, not authentication: `devin skills list`
    # reads local config and makes no API call, so a logged-out Devin whose
    # skills dir resolves correctly is fine, and `devin models list` would have
    # refused on a perfectly healthy machine.
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    mkdir -p "$SANDBOX/bin"
    printf '#!/bin/sh\necho "no skills here"\n' > "$SANDBOX/bin/devin"
    chmod +x "$SANDBOX/bin/devin"
    run env PATH="$SANDBOX/bin:$PATH" "$SCRIPT" manifest-docs
    assert_failure
    assert_output --partial "does not report any skill"
}

@test "the Devin refusal names the escape hatch" {
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    mkdir -p "$SANDBOX/bin"
    printf '#!/bin/sh\necho "no skills here"\n' > "$SANDBOX/bin/devin"
    chmod +x "$SANDBOX/bin/devin"
    run env PATH="$SANDBOX/bin:$PATH" "$SCRIPT" manifest-docs
    assert_output --partial "--allow-unverified-devin"
}

@test "the gate creates the Devin link and proceeds once Devin reports the tree" {
    # The direction that proves the gate is a gate. A check that always refuses
    # is indistinguishable from a working one until someone needs it to pass.
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    mkdir -p "$SANDBOX/bin"
    printf '#!/bin/sh\necho "  /alpha (%s/alpha)"\n' "$MANIFEST_SKILLS_DIR" \
        > "$SANDBOX/bin/devin"
    chmod +x "$SANDBOX/bin/devin"
    run env PATH="$SANDBOX/bin:$PATH" "$SCRIPT" manifest-docs
    refute_output --partial "does not report any skill"
    [ "$(readlink "$DEVIN_SKILLS_LINK")" = "$MANIFEST_SKILLS_DIR" ]
}

@test "the gate never touches a path outside its configured roots" {
    # The defect this closes: the tests do not override HOME, so the first
    # version of this gate created a REAL ~/.config/devin/skills pointing into a
    # sandbox that teardown then deleted -- and the suite still reported green.
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    mkdir -p "$SANDBOX/bin"
    printf '#!/bin/sh\necho "  /alpha (%s/alpha)"\n' "$MANIFEST_SKILLS_DIR" \
        > "$SANDBOX/bin/devin"
    chmod +x "$SANDBOX/bin/devin"
    run env PATH="$SANDBOX/bin:$PATH" "$SCRIPT" manifest-docs
    [ ! -e "$HOME/.config/devin/skills" ]
}

@test "a real directory at the Devin path is never clobbered" {
    # Devin serving its own skills there is the user's own state.
    : > "$MANIFEST_STATE_DIR/pre-cutover-20260101_000000.tgz"
    mkdir -p "$DEVIN_SKILLS_LINK/its-own" "$SANDBOX/bin"
    printf '#!/bin/sh\necho x\n' > "$SANDBOX/bin/devin"
    chmod +x "$SANDBOX/bin/devin"
    run env PATH="$SANDBOX/bin:$PATH" "$SCRIPT" manifest-docs
    assert_failure
    assert_output --partial "not a symlink"
    [ -d "$DEVIN_SKILLS_LINK/its-own" ]
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
