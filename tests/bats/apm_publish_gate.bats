#!/usr/bin/env bats
# Tests for configs/claude/scripts/apm_publish_gate.sh (T048/FR-030 scan,
# T049/FR-038 provenance, `all`/SC-011 gate record).
#
# Every fixture lives under a per-test mktemp sandbox and is torn down after
# the test; nothing here reads or writes the real repo state, the real
# gate-records.jsonl, or real $HOME. Git fixture repos pin
# tag.gpgsign/commit.gpgsign off via GIT_CONFIG_* env overrides so the suite
# does not depend on (or fight) the operator's global git config.
#
# Seeded secrets are built at RUNTIME (never as a contiguous literal in this
# file) so the exact gitleaks-matching string never appears in a committed
# file the repo's own gitleaks pre-commit hook would scan.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'
load '../test_helper/git_fixture.bash'

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/apm_publish_gate.sh"
ALLOWLIST="$BATS_TEST_DIRNAME/../../configs/claude/config/apm_publish_allowlist.txt"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_publish_gate.XXXXXX")"
    git_fixture_env
}

teardown() {
    git_fixture_unset
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# fake_github_pat -> an obviously-fake but gitleaks-github-pat-rule-matching
# token, assembled at runtime so the full matching string is never a
# contiguous literal anywhere in this source file.
fake_github_pat() {
    printf 'ghp_%s' "$(python3 -c "print('0' * 36)")"
}

# gitleaks_stub_path -> a temp bin dir on PATH ahead of the real gitleaks,
# containing a `gitleaks` that always exits 127. Simulates "gitleaks absent
# or erroring" without PATH-subtraction (which breaks on merged-/usr
# runners): the stub IS found by `command -v`, but fails when invoked.
gitleaks_stub_path() {
    local bin="$SANDBOX/stubbin"
    mkdir -p "$bin"
    {
        echo '#!/usr/bin/env bash'
        echo 'exit 127'
    } > "$bin/gitleaks"
    chmod +x "$bin/gitleaks"
    printf '%s' "$bin"
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
    # Real repo convention (docs/CODING_STANDARDS.md): verify --help with an
    # empty HOME, not the operator's, so a script that secretly depends on
    # ~/.claude state can't pass locally and fail in CI.
    run env -i PATH="$PATH" HOME="$SANDBOX/no-such-home" "$SCRIPT" --help
    assert_success
    assert_output --partial "Usage"
}

@test "no subcommand is a usage error (exit 2)" {
    run "$SCRIPT"
    assert_failure 2
}

@test "unknown subcommand is a usage error (exit 2)" {
    run "$SCRIPT" bogus
    assert_failure 2
}

@test "scan with no PATH argument is a usage error (exit 2)" {
    run "$SCRIPT" scan
    assert_failure 2
}

# --- scan: detection (genuine seeded violations) ---

@test "scan: clean tree passes" {
    mkdir -p "$SANDBOX/clean_pkg"
    echo "just a normal readme, nothing sensitive" > "$SANDBOX/clean_pkg/README.md"
    run "$SCRIPT" scan "$SANDBOX/clean_pkg"
    assert_success
}

@test "scan: rejects a planted fake secret (gitleaks github-pat rule)" {
    mkdir -p "$SANDBOX/secret_pkg"
    printf 'token: %s\n' "$(fake_github_pat)" > "$SANDBOX/secret_pkg/leak.txt"
    # Precondition: the planted violation is genuinely present before we
    # assert the gate catches it (no vacuous pass).
    grep -q "ghp_" "$SANDBOX/secret_pkg/leak.txt"

    run "$SCRIPT" scan "$SANDBOX/secret_pkg"
    assert_failure 1
    assert_output --partial "gitleaks"
}

@test "scan: rejects a planted machine-local /Users/<realname> path" {
    mkdir -p "$SANDBOX/path_pkg"
    echo "see /Users/alice-cddl-fixture/private-notes.md for context" > "$SANDBOX/path_pkg/doc.md"
    # Precondition: the planted path is genuinely present in the fixture.
    grep -q "/Users/alice-cddl-fixture" "$SANDBOX/path_pkg/doc.md"

    run "$SCRIPT" scan "$SANDBOX/path_pkg"
    assert_failure 1
    assert_output --partial "machine-local-path"
}

@test "scan: true negative — real committed allowlist active, a non-placeholder path still blocks (F1 regression guard)" {
    # The real committed allowlist.txt (not overridden here) contains
    # blank/comment lines by design (Decision D's documentation), which is
    # exactly the shape that broke on GNU grep before the F1 fix. Precondition
    # confirms the allowlist genuinely has a blank line, so this test
    # exercises the real F1 scenario rather than an idealized one.
    grep -q '^[[:space:]]*$' "$ALLOWLIST"

    mkdir -p "$SANDBOX/real_path_pkg"
    echo "see /Users/definitely-not-a-placeholder-fixture/notes.md" > "$SANDBOX/real_path_pkg/doc.md"
    grep -q "/Users/definitely-not-a-placeholder-fixture" "$SANDBOX/real_path_pkg/doc.md"

    run "$SCRIPT" scan "$SANDBOX/real_path_pkg"
    assert_failure 1
    assert_output --partial "machine-local-path"
}

@test "scan: rejects a planted .remember/ reference" {
    mkdir -p "$SANDBOX/remember_pkg"
    echo "loaded from .remember/notes.md at session start" > "$SANDBOX/remember_pkg/doc.md"
    grep -q "\.remember/" "$SANDBOX/remember_pkg/doc.md"

    run "$SCRIPT" scan "$SANDBOX/remember_pkg"
    assert_failure 1
    assert_output --partial "private-remember-ref"
}

# --- scan: allowlist (F1 filter-safety + F2 reachability) ---

@test "scan: documentation placeholder — precondition: without an allowlist it is genuinely flagged" {
    # Establishes the "before" state Standing Constraint 6 requires: with no
    # allowlist in effect, the placeholder text really is detected as a
    # machine-local-path hit (proving the allowlist test below suppresses a
    # real hit, not a no-op).
    mkdir -p "$SANDBOX/doc_pkg"
    echo 'example: config lives at /Users/<name>/.claude/config.yml' > "$SANDBOX/doc_pkg/doc.md"

    run env APM_PUBLISH_ALLOWLIST="$SANDBOX/no-such-allowlist.txt" "$SCRIPT" scan "$SANDBOX/doc_pkg"
    assert_failure 1
    assert_output --partial "machine-local-path"
}

@test "scan: documentation placeholder is suppressed by the real committed allowlist" {
    mkdir -p "$SANDBOX/doc_pkg2"
    echo 'example: config lives at /Users/<name>/.claude/config.yml' > "$SANDBOX/doc_pkg2/doc.md"

    run "$SCRIPT" scan "$SANDBOX/doc_pkg2"
    assert_success
}

@test "scan: allowlist filtering — blank/comment lines in the allowlist do not suppress unrelated hits" {
    # A dedicated unit test of the filter logic itself (F1): a custom
    # allowlist deliberately interleaves blank lines, a comment line, and
    # one real pattern. If blank lines were still handed to `grep -f`
    # unfiltered, an empty pattern would match everything and BOTH files
    # below would be suppressed. The fix must suppress only the file that
    # legitimately matches the one real pattern.
    mkdir -p "$SANDBOX/filter_pkg"
    echo "see /Users/<name>/.claude/config.yml for an example" > "$SANDBOX/filter_pkg/allowed.md"
    echo "see /Users/definitely-real-fixture-user/private-notes.md" > "$SANDBOX/filter_pkg/blocked.md"

    local custom_allowlist="$SANDBOX/custom-allowlist.txt"
    {
        echo ""
        echo "# a comment line"
        echo "   "
        echo '^/Users/<name>(/.*)?$'
        echo ""
    } > "$custom_allowlist"
    # Precondition: the custom allowlist genuinely contains blank lines.
    grep -q '^[[:space:]]*$' "$custom_allowlist"

    run env APM_PUBLISH_ALLOWLIST="$custom_allowlist" "$SCRIPT" scan "$SANDBOX/filter_pkg"
    assert_failure 1
    assert_output --partial "blocked.md"
    refute_output --partial "allowed.md"
}

@test "scan: allowlist filtering — an allowlist that is all blank/comment lines suppresses nothing (not an error)" {
    # The "empty after filtering" path F1 calls out explicitly: a file that
    # exists and is non-empty on disk but reduces to zero real patterns
    # after stripping blanks/comments must behave exactly like "no
    # allowlist" (every hit reported), not like "match everything" and not
    # like a scan error.
    mkdir -p "$SANDBOX/allblank_pkg"
    echo "see /Users/definitely-real-fixture-user/private-notes.md" > "$SANDBOX/allblank_pkg/doc.md"

    local blank_allowlist="$SANDBOX/allblank-allowlist.txt"
    {
        echo ""
        echo "# only comments and blanks here"
        echo ""
    } > "$blank_allowlist"

    run env APM_PUBLISH_ALLOWLIST="$blank_allowlist" "$SCRIPT" scan "$SANDBOX/allblank_pkg"
    assert_failure 1
    assert_output --partial "machine-local-path"
}

# --- scan: NUL-safe walk (F7 regression guard) ---

@test "scan: a filename with an embedded newline still triggers Decision-D detection (F7)" {
    # F7: apm_walk_tree_files used to be line-oriented (find -print | sed |
    # sort). A filename containing a literal embedded newline (legal on
    # APFS) split into two synthetic relative paths, neither of which
    # resolved to a real file, so the real file's content was never opened
    # or grepped by any Decision-D category — cmd_scan could PASS a tree
    # whose newline-named file held private material. The walk is now
    # NUL-delimited end to end; this proves the fix by planting a genuine
    # private-email violation inside a newline-named file's CONTENT. Use a
    # real-looking domain — not @example.com/@*.test (RFC 2606 allowlisted
    # since 1f8fd26) — so the hit is not suppressed before F7 is exercised.
    mkdir -p "$SANDBOX/newline_pkg"
    local evil_name
    evil_name=$'evil\nleak.txt'
    local evil_path="$SANDBOX/newline_pkg/$evil_name"
    printf 'contact me at exposed-operator-fixture@realcorp-fixture.com for details\n' > "$evil_path"

    if [ ! -f "$evil_path" ]; then
        skip "this platform/filesystem could not create a filename with an embedded newline"
    fi

    # Precondition: the file's CONTENT genuinely matches the Decision-D
    # private-email pattern when grepped directly — proves this is not a
    # vacuous fixture (Standing Constraint 6).
    grep -q "exposed-operator-fixture@realcorp-fixture.com" "$evil_path"

    run "$SCRIPT" scan "$SANDBOX/newline_pkg"
    assert_failure 1
    assert_output --partial "private-email"
}

# --- scan: fail-closed on indeterminate ---

@test "scan: gitleaks missing/erroring (exit-127 stub) rejects, no regex-only degrade" {
    mkdir -p "$SANDBOX/clean_pkg2"
    echo "nothing sensitive here" > "$SANDBOX/clean_pkg2/README.md"
    local stub
    stub="$(gitleaks_stub_path)"
    run env PATH="$stub:$PATH" "$SCRIPT" scan "$SANDBOX/clean_pkg2"
    assert_failure 1
    assert_output --partial "gitleaks"
}

@test "scan: nonexistent PATH is indeterminate, rejects (exit 1, not 2)" {
    run "$SCRIPT" scan "$SANDBOX/does-not-exist"
    assert_failure 1
}

@test "scan: unreadable target directory rejects" {
    mkdir -p "$SANDBOX/locked_pkg"
    chmod 000 "$SANDBOX/locked_pkg"
    run "$SCRIPT" scan "$SANDBOX/locked_pkg"
    chmod 755 "$SANDBOX/locked_pkg"
    assert_failure 1
}

# --- provenance ---

make_tagged_repo() {
    local repo="$1"
    mkdir -p "$repo"
    git -C "$repo" init -q -b main
    git -C "$repo" commit -q --allow-empty -m init
    git -C "$repo" tag v0.1.0
}

@test "provenance: not a git repository is indeterminate, rejects" {
    mkdir -p "$SANDBOX/notarepo"
    run env APM_GATE_REPO="$SANDBOX/notarepo" "$SCRIPT" provenance
    assert_failure 1
}

@test "provenance: clean tree at a tagged commit passes" {
    make_tagged_repo "$SANDBOX/repo_clean"
    run env APM_GATE_REPO="$SANDBOX/repo_clean" "$SCRIPT" provenance
    assert_success
    assert_output --partial "v0.1.0"
}

@test "provenance: dirty working tree rejects (precondition: tree is genuinely dirty)" {
    make_tagged_repo "$SANDBOX/repo_dirty"
    echo "uncommitted" > "$SANDBOX/repo_dirty/scratch.txt"
    # Precondition: git itself reports this tree as dirty.
    [ -n "$(git -C "$SANDBOX/repo_dirty" status --porcelain)" ]

    run env APM_GATE_REPO="$SANDBOX/repo_dirty" "$SCRIPT" provenance
    assert_failure 1
}

@test "provenance: untagged HEAD rejects (precondition: HEAD has no tag)" {
    make_tagged_repo "$SANDBOX/repo_untagged"
    git -C "$SANDBOX/repo_untagged" commit -q --allow-empty -m "second, untagged"
    # Precondition: HEAD is genuinely not at any tag.
    run git -C "$SANDBOX/repo_untagged" describe --tags --exact-match
    assert_failure

    run env APM_GATE_REPO="$SANDBOX/repo_untagged" "$SCRIPT" provenance
    assert_failure 1
}

# --- all: composed gate + gate-record ---

@test "all: pass appends a well-formed JSONL pass record" {
    make_tagged_repo "$SANDBOX/repo_all_pass"
    mkdir -p "$SANDBOX/pkg_all_pass"
    echo "clean package content" > "$SANDBOX/pkg_all_pass/README.md"
    local records="$SANDBOX/gate-records.jsonl"

    run env APM_GATE_REPO="$SANDBOX/repo_all_pass" APM_GATE_RECORD_FILE="$records" \
        "$SCRIPT" all "$SANDBOX/pkg_all_pass"
    assert_success

    [ -f "$records" ]
    [ "$(wc -l < "$records" | tr -d ' ')" -eq 1 ]
    run python3 -c "
import json, sys
rec = json.loads(open('$records').readline())
assert rec['result'] == 'pass', rec
assert rec['git_ref'] == 'v0.1.0', rec
assert isinstance(rec['subject_sha256'], str) and len(rec['subject_sha256']) == 64, rec
assert rec['gate'] == 'apm_publish_gate.all', rec
for k in ('ts', 'subject', 'tool_version'):
    assert rec.get(k), rec
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "all: a rejected attempt still appends a fail record (SC-011 audit trail)" {
    make_tagged_repo "$SANDBOX/repo_all_fail"
    echo "uncommitted" > "$SANDBOX/repo_all_fail/scratch.txt"
    mkdir -p "$SANDBOX/pkg_all_fail"
    printf 'token: %s\n' "$(fake_github_pat)" > "$SANDBOX/pkg_all_fail/leak.txt"
    local records="$SANDBOX/gate-records-fail.jsonl"

    run env APM_GATE_REPO="$SANDBOX/repo_all_fail" APM_GATE_RECORD_FILE="$records" \
        "$SCRIPT" all "$SANDBOX/pkg_all_fail"
    assert_failure 1

    [ -f "$records" ]
    run python3 -c "
import json
rec = json.loads(open('$records').readline())
assert rec['result'] == 'fail', rec
print('ok')
"
    assert_success
    assert_output --partial "ok"
}

@test "all with no PATH argument is a usage error (exit 2)" {
    run "$SCRIPT" all
    assert_failure 2
}
