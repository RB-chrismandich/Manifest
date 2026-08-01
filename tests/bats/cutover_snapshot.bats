#!/usr/bin/env bats
# T0.1 (spec 674) — the mechanism-independent restore path for the plugin cutover.
#
# This exists because every rollback the four cutover designs proposed is
# CIRCULAR: they call `apm_ungate_domain.sh skills --apply` or `apm-dev-sync`,
# both of which the cutover retires, and apm_ungate_domain.sh additionally
# guards on the registry entry it is trying to restore, so it exits 1 once that
# entry moves to `retired:`. A snapshot that depends on bootstrap, apm or the
# plugin CLI is therefore not a rollback at all — it is a second thing to
# restore. Hence: plain tar, plain find, no repo state, no network.
#
# The load-bearing test here is "verify fails on a doctored sidecar". A --verify
# that cannot fail is the exact false-green this whole phase exists to remove,
# and per this repo's mutation-verify rule a guard is not coverage until it has
# been watched to fail.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SNAP="$REPO_ROOT/configs/claude/scripts/cutover_snapshot.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/cutover_snap.XXXXXX")"
    export HOME="$SANDBOX/home"
    export MANIFEST_STATE_DIR="$HOME/.manifest"

    mkdir -p "$HOME/.claude/skills/alpha" "$HOME/.claude/skills/beta" "$HOME/.apm"
    printf 'name: alpha\n' > "$HOME/.claude/skills/alpha/SKILL.md"
    printf 'name: beta\n' > "$HOME/.claude/skills/beta/SKILL.md"
    printf '{"model":"opus"}\n' > "$HOME/.claude/settings.json"
    printf 'dependencies: {}\n' > "$HOME/.apm/apm.lock.yaml"
    printf 'targets: []\n' > "$HOME/.apm/apm.yml"

    # The four sibling homes are symlinks to ~/.claude/skills on a real machine.
    local d
    for d in .cursor .gemini .codex .antigravity; do
        mkdir -p "$HOME/$d"
        ln -s "$HOME/.claude/skills" "$HOME/$d/skills"
    done
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

# --- help path -------------------------------------------------------------
# Must answer before any config/state lookup: a --help that needs a populated
# HOME is useless in exactly the situation you reach for it.

@test "--help exits 0 and prints usage" {
    run "$SNAP" --help
    assert_success
    assert_output --partial "Usage: cutover_snapshot.sh"
}

@test "--help works with a completely empty HOME" {
    export HOME="$SANDBOX/empty"
    mkdir -p "$HOME"
    run "$SNAP" --help
    assert_success
}

@test "--help is at most 15 lines (repo convention)" {
    run "$SNAP" --help
    assert_success
    [ "${#lines[@]}" -le 15 ]
}

# --- snapshot creation -----------------------------------------------------

@test "creates a tarball and a sidecar under MANIFEST_STATE_DIR" {
    run "$SNAP"
    assert_success
    local tgz
    tgz="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.tgz' | head -1)"
    [ -s "$tgz" ]
    [ -s "${tgz%.tgz}.txt" ]
}

@test "sidecar records the SKILL.md count" {
    run "$SNAP"
    assert_success
    local txt
    txt="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.txt' | head -1)"
    grep -qx 'skill_count=2' "$txt"
}

@test "sidecar records each sibling home's skills readlink" {
    run "$SNAP"
    assert_success
    local txt
    txt="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.txt' | head -1)"
    local d
    for d in cursor gemini codex antigravity; do
        grep -q "^readlink_${d}=${HOME}/.claude/skills$" "$txt"
    done
}

@test "tarball contains the skills tree and settings.json" {
    run "$SNAP"
    assert_success
    local tgz
    tgz="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.tgz' | head -1)"
    run tar tzf "$tgz"
    assert_success
    assert_output --partial ".claude/skills/alpha/SKILL.md"
    assert_output --partial ".claude/settings.json"
}

@test "absent optional files do not fail the snapshot" {
    # ~/.config/devin/config.json does not exist in this sandbox, and on a
    # default machine Devin is disabled, so this is the common case, not an edge.
    run "$SNAP"
    assert_success
}

# --- verify ----------------------------------------------------------------

@test "--verify succeeds on a freshly written snapshot" {
    run "$SNAP"
    assert_success
    run "$SNAP" --verify
    assert_success
    assert_output --partial "OK"
}

@test "--verify FAILS when the recorded count disagrees with the tarball" {
    # Mutation-verify: this is the assertion the whole task exists for. If it
    # cannot fail, --verify is decoration and the rollback is unproven.
    run "$SNAP"
    assert_success
    local txt
    txt="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.txt' | head -1)"
    sed 's/^skill_count=2$/skill_count=99/' "$txt" > "$txt.new" && mv "$txt.new" "$txt"

    run "$SNAP" --verify
    assert_failure
    assert_output --partial "99"
}

@test "--verify fails when no snapshot exists" {
    run "$SNAP" --verify
    assert_failure
}

# --- verify must cover what it captured ------------------------------------
# The first --verify asserted ONE thing: the SKILL.md count. It passed an
# archive whose settings.json was garbage and whose apm.lock.yaml, apm.yml and
# installed_plugins.json had been deleted outright -- reproduced, exit 0, "OK".
# For the only rollback that survives Phase 5, proving the skills subtree
# round-tripped is not proving the snapshot is restorable. Every path the
# snapshot captured is now re-checked on the way back out.

@test "--verify fails when a captured file is missing from the archive" {
    run "$SNAP"
    assert_success
    local tgz txt work
    tgz="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.tgz' | head -1)"
    txt="${tgz%.tgz}.txt"
    work="$SANDBOX/rebuild"
    mkdir -p "$work"
    tar xzf "$tgz" -C "$work"
    rm -f "$work/.apm/apm.lock.yaml"
    tar czf "$tgz" -C "$work" .claude .apm

    run "$SNAP" --verify
    assert_failure
    assert_output --partial "apm.lock.yaml"
}

@test "--verify fails when a captured file is present but empty" {
    run "$SNAP"
    assert_success
    local tgz work
    tgz="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.tgz' | head -1)"
    work="$SANDBOX/rebuild2"
    mkdir -p "$work"
    tar xzf "$tgz" -C "$work"
    : > "$work/.claude/settings.json"
    tar czf "$tgz" -C "$work" .claude .apm

    run "$SNAP" --verify
    assert_failure
    assert_output --partial "settings.json"
}

@test "--verify fails when settings.json is not parseable JSON" {
    # A restore that puts back a corrupt settings.json is not a restore. This
    # is the case that motivated widening the check.
    run "$SNAP"
    assert_success
    local tgz work
    tgz="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.tgz' | head -1)"
    work="$SANDBOX/rebuild3"
    mkdir -p "$work"
    tar xzf "$tgz" -C "$work"
    printf 'THIS IS NOT VALID JSON {{{' > "$work/.claude/settings.json"
    tar czf "$tgz" -C "$work" .claude .apm

    run "$SNAP" --verify
    assert_failure
    assert_output --partial "settings.json"
}

@test "--verify only requires files the sidecar recorded as captured" {
    # ~/.config/devin/config.json is absent in this sandbox and on a default
    # machine. Demanding it back would make --verify fail on a correct snapshot.
    run "$SNAP"
    assert_success
    run "$SNAP" --verify
    assert_success
}

@test "--verify fails on a truncated tarball" {
    run "$SNAP"
    assert_success
    local tgz
    tgz="$(find "$MANIFEST_STATE_DIR" -name 'pre-cutover-*.tgz' | head -1)"
    printf 'corrupt' > "$tgz"
    run "$SNAP" --verify
    assert_failure
}

# --- independence ----------------------------------------------------------

@test "does not invoke apm, bootstrap or the claude CLI" {
    # The premise of the whole task: a restore path that shares a dependency
    # with the thing being migrated is not a restore path.
    #
    # Comments are stripped first. The header NAMES apm_ungate_domain.sh and
    # apm-dev-sync deliberately — explaining why they are unusable is the point
    # of the file — so grepping raw source tests the prose, not the behaviour.
    run bash -c "grep -vE '^[[:space:]]*#' '$SNAP' |
                 grep -nE '(apm-dev-sync|apm_ungate_domain|bootstrap\.sh|claude plugin|apm install)'"
    assert_failure
}
