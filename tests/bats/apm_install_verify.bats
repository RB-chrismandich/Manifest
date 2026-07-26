#!/usr/bin/env bats
# Tests for configs/claude/scripts/apm_install_verify.sh (T050/FR-018:
# install-time package integrity verification).
#
# Every fixture lives under a per-test mktemp sandbox and is torn down after
# the test; nothing here reads or writes the real repo state, the real
# gate-records.jsonl, or real $HOME. Gate records used as fixtures are
# produced by the real apm_publish_gate.sh (dogfooding the publish side)
# so the two scripts are proven compatible with each other, not just
# internally consistent.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'
load '../test_helper/git_fixture.bash'

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/apm_install_verify.sh"
GATE_SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/apm_publish_gate.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_install_verify.XXXXXX")"
    git_fixture_env

    # A real, passing gate record produced by the actual publish gate, so
    # install-verify tests exercise genuine cross-script compatibility.
    REPO="$SANDBOX/repo"
    mkdir -p "$REPO"
    git -C "$REPO" init -q -b main
    git -C "$REPO" commit -q --allow-empty -m init
    git -C "$REPO" tag v1.0.0
    REF="v1.0.0"

    PKG="$SANDBOX/pkg"
    mkdir -p "$PKG/sub"
    echo "primitive one" > "$PKG/agent.md"
    echo "primitive two" > "$PKG/sub/hook.sh"

    RECORDS="$SANDBOX/gate-records.jsonl"
    APM_GATE_REPO="$REPO" APM_GATE_RECORD_FILE="$RECORDS" "$GATE_SCRIPT" all "$PKG" > /dev/null
}

teardown() {
    git_fixture_unset
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# --- CLI surface ---

@test "--help exits 0, prints Usage, <=15 lines" {
    run "$SCRIPT" --help
    assert_success
    assert_output --partial "Usage"
    local lines
    lines=$(printf '%s\n' "$output" | wc -l | tr -d ' ')
    [ "$lines" -le 15 ] || { echo "help is $lines lines"; false; }
}

@test "--help works before any config/state lookup (empty, non-existent HOME)" {
    run env -i PATH="$PATH" HOME="$SANDBOX/no-such-home" "$SCRIPT" --help
    assert_success
    assert_output --partial "Usage"
}

@test "no subcommand is a usage error (exit 2)" {
    run "$SCRIPT"
    assert_failure 2
}

@test "verify with no TREE_PATH is a usage error (exit 2)" {
    run "$SCRIPT" verify
    assert_failure 2
}

@test "verify with no --ref is a usage error (exit 2)" {
    run "$SCRIPT" verify "$PKG"
    assert_failure 2
}

# --- precondition sanity: the fixture record is genuinely usable ---

@test "fixture setup produced exactly one pass record for REF" {
    [ -f "$RECORDS" ]
    run python3 -c "
import json
recs = [json.loads(l) for l in open('$RECORDS') if l.strip()]
matching = [r for r in recs if r.get('git_ref') == '$REF' and r.get('result') == 'pass']
assert len(matching) == 1, matching
assert matching[0]['subject_sha256']
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

# --- happy path ---

@test "verify: an untampered installed tree matches its recorded hash" {
    INSTALLED="$SANDBOX/installed"
    cp -R "$PKG" "$INSTALLED"
    run "$SCRIPT" verify "$INSTALLED" --ref "$REF" --records "$RECORDS"
    assert_success
    assert_output --partial "OK"
}

@test "verify: APM_GATE_RECORD_FILE env var is honored when --records is omitted" {
    INSTALLED="$SANDBOX/installed2"
    cp -R "$PKG" "$INSTALLED"
    run env APM_GATE_RECORD_FILE="$RECORDS" "$SCRIPT" verify "$INSTALLED" --ref "$REF"
    assert_success
}

# --- NUL-safe walk (F7 regression guard): hash-path symmetry ---

@test "hash: a filename with an embedded newline hashes deterministically under the NUL-safe walk (F7)" {
    # F7 companion check: apm_walk_tree_files (apm_hash_lib.sh) is shared by
    # both the publish-gate scan (apm_publish_gate.bats covers the scan
    # side: an embedded-newline filename's CONTENT must still be grepped)
    # and this hash routine. Proves the shared NUL-safe walk didn't just
    # move the bug from scan to hash: the hash routine must resolve the
    # real file (not fail closed on a synthetic split path) and be
    # deterministic across independent calls on the identical fixture.
    mkdir -p "$SANDBOX/newline_hash_pkg"
    local evil_name
    evil_name=$'weird\nname.txt'
    local evil_path="$SANDBOX/newline_hash_pkg/$evil_name"
    printf 'benign content, no Decision-D violation here\n' > "$evil_path"
    echo "normal file" > "$SANDBOX/newline_hash_pkg/normal.txt"

    if [ ! -f "$evil_path" ]; then
        skip "this platform/filesystem could not create a filename with an embedded newline"
    fi
    # Precondition: the fixture genuinely contains both distinct files
    # (checked individually — a newline-splitting `find | wc -l` would
    # miscount the embedded-newline filename as two lines and pass
    # vacuously even if the walk still mis-enumerated it).
    [ -f "$SANDBOX/newline_hash_pkg/normal.txt" ]

    HASH_LIB="$BATS_TEST_DIRNAME/../../configs/claude/scripts/apm_hash_lib.sh"
    # shellcheck disable=SC1090
    source "$HASH_LIB"
    local h1 h2
    h1="$(apm_canonical_tree_hash "$SANDBOX/newline_hash_pkg")"
    h2="$(apm_canonical_tree_hash "$SANDBOX/newline_hash_pkg")"

    [ -n "$h1" ]
    [ "${#h1}" -eq 64 ]
    [ "$h1" = "$h2" ]
}

@test "all + verify: a newline-named file round-trips through publish and install (scan and hash agree on the walk)" {
    # End-to-end companion to the unit check above: the real
    # apm_publish_gate.sh (publish side) and apm_install_verify.sh (install
    # side) must independently compute the same canonical hash for a tree
    # containing an embedded-newline filename, via the one shared walk.
    REPO2="$SANDBOX/repo2"
    mkdir -p "$REPO2"
    git -C "$REPO2" init -q -b main
    git -C "$REPO2" commit -q --allow-empty -m init
    git -C "$REPO2" tag v2.0.0

    PKG2="$SANDBOX/pkg2"
    mkdir -p "$PKG2"
    local evil_name
    evil_name=$'weird\nname.txt'
    local evil_path="$PKG2/$evil_name"
    printf 'benign content, no Decision-D violation here\n' > "$evil_path"
    echo "normal file" > "$PKG2/normal.txt"

    if [ ! -f "$evil_path" ]; then
        skip "this platform/filesystem could not create a filename with an embedded newline"
    fi

    RECORDS2="$SANDBOX/gate-records2.jsonl"
    run env APM_GATE_REPO="$REPO2" APM_GATE_RECORD_FILE="$RECORDS2" "$GATE_SCRIPT" all "$PKG2"
    assert_success

    INSTALLED2="$SANDBOX/installed_pkg2"
    cp -R "$PKG2" "$INSTALLED2"
    # Precondition: the copy genuinely preserved the embedded-newline
    # filename (cp -R does not mangle it into two files) and the normal one.
    [ -f "$INSTALLED2/$evil_name" ]
    [ -f "$INSTALLED2/normal.txt" ]

    run "$SCRIPT" verify "$INSTALLED2" --ref "v2.0.0" --records "$RECORDS2"
    assert_success
    assert_output --partial "OK"
}

# --- detection: genuine tampering ---

@test "verify: rejects a tampered tree (precondition: tree genuinely differs from source)" {
    TAMPERED="$SANDBOX/tampered"
    cp -R "$PKG" "$TAMPERED"
    echo "malicious appended content" >> "$TAMPERED/agent.md"

    # Precondition: the tampered tree is genuinely different from the
    # original package the gate record describes.
    ! diff -r "$PKG" "$TAMPERED" > /dev/null 2>&1

    run "$SCRIPT" verify "$TAMPERED" --ref "$REF" --records "$RECORDS"
    assert_failure 1
    assert_output --partial "mismatch"
}

@test "verify: rejects a tree with an extra file not in the published tree" {
    TAMPERED="$SANDBOX/tampered_extra"
    cp -R "$PKG" "$TAMPERED"
    echo "smuggled" > "$TAMPERED/extra-file.txt"
    [ -f "$TAMPERED/extra-file.txt" ]

    run "$SCRIPT" verify "$TAMPERED" --ref "$REF" --records "$RECORDS"
    assert_failure 1
}

# --- fail-closed on indeterminate ---

@test "verify: absent records file is indeterminate, rejects" {
    run "$SCRIPT" verify "$PKG" --ref "$REF" --records "$SANDBOX/no-such-file.jsonl"
    assert_failure 1
}

@test "verify: no record for the requested ref is indeterminate, rejects" {
    run "$SCRIPT" verify "$PKG" --ref "v9.9.9-does-not-exist" --records "$RECORDS"
    assert_failure 1
}

@test "verify: ambiguous match (two conflicting hashes for one ref) rejects" {
    AMBIGUOUS="$SANDBOX/ambiguous-records.jsonl"
    cp "$RECORDS" "$AMBIGUOUS"
    # A second, conflicting pass record for the SAME ref with a different
    # hash — a genuine, detectable conflict, not a rerun duplicate.
    python3 -c "
import json
rec = json.loads(open('$RECORDS').readline())
rec['subject_sha256'] = 'f' * 64
print(json.dumps(rec))
" >> "$AMBIGUOUS"
    # Precondition: two distinct pass records now exist for REF.
    run python3 -c "
import json
recs = [json.loads(l) for l in open('$AMBIGUOUS') if l.strip()]
hashes = {r['subject_sha256'] for r in recs if r.get('git_ref') == '$REF' and r.get('result') == 'pass'}
assert len(hashes) == 2, hashes
"
    assert_success

    run "$SCRIPT" verify "$PKG" --ref "$REF" --records "$AMBIGUOUS"
    assert_failure 1
}

@test "verify: a duplicate identical pass record for one ref is NOT ambiguous" {
    DUPED="$SANDBOX/duped-records.jsonl"
    cat "$RECORDS" "$RECORDS" > "$DUPED"
    INSTALLED="$SANDBOX/installed3"
    cp -R "$PKG" "$INSTALLED"
    run "$SCRIPT" verify "$INSTALLED" --ref "$REF" --records "$DUPED"
    assert_success
}

@test "verify: unreadable tree is indeterminate, rejects" {
    LOCKED="$SANDBOX/locked"
    cp -R "$PKG" "$LOCKED"
    chmod 000 "$LOCKED/agent.md"
    run "$SCRIPT" verify "$LOCKED" --ref "$REF" --records "$RECORDS"
    chmod 644 "$LOCKED/agent.md"
    assert_failure 1
}

@test "verify: nonexistent tree path is indeterminate, rejects" {
    run "$SCRIPT" verify "$SANDBOX/does-not-exist" --ref "$REF" --records "$RECORDS"
    assert_failure 1
}
