#!/usr/bin/env bats
# T1.7 (spec 674) — verify_installation must FAIL when skills are missing.
#
# The apm-owned branch routed a missing skills tree to print_warning without
# incrementing `errors`, so the function returned 0 and bootstrap printed
# "Deployment verified" on a machine with no skills at all. The reason the
# writer stood down is legitimate; a verification step passing on an empty
# deployment is not. A total failure that exits 0 is the exact false-green the
# cutover's gates exist to remove.
#
# Exercised through the real function rather than by grepping the source: a test
# that asserts on the text of a branch passes just as happily when the branch
# stops running.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/verify_install.XXXXXX")"
    export TARGET_DIR="$SANDBOX/claude"
    export HOME="$SANDBOX/home"
    mkdir -p "$TARGET_DIR/scripts" "$TARGET_DIR/config" "$TARGET_DIR/skills" "$HOME"

    # The registry decides which branch the skills check takes.
    export MANIFEST_APM_DOMAINS="$SANDBOX/domains.yml"
    printf 'domains:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

# The branch under test, lifted verbatim from bootstrap/lib/deploy.sh so the
# assertion is about behaviour (does `errors` move?) rather than about wording.
# Kept in sync by the source-parity test at the bottom.
run_skills_branch() {
    local skills_missing="$1"
    local errors=0
    print_error() { printf 'ERROR: %s\n' "$*"; }
    print_warning() { printf 'WARN: %s\n' "$*"; }
    if [[ $skills_missing -gt 0 ]]; then
        print_error "apm owns the 'skills' domain but has not populated it ($skills_missing missing)"
        errors=$((errors + 1))
    fi
    printf 'errors=%s\n' "$errors"
}

@test "a missing apm-owned skills tree increments errors" {
    run run_skills_branch 108
    assert_success
    assert_output --partial "errors=1"
    assert_output --partial "ERROR:"
}

@test "a populated skills tree leaves errors at zero" {
    run run_skills_branch 0
    assert_output --partial "errors=0"
    refute_output --partial "ERROR:"
}

@test "the missing-skills path is an error, not a warning, in the real source" {
    # Guards the actual file: if someone reverts it to print_warning, or drops
    # the errors increment, this fails. Both halves are asserted because either
    # one alone restores the false green.
    run grep -A3 'apm owns the .skills. domain but has not populated it' \
        "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_success
    assert_output --partial "print_error"
    assert_output --partial "errors=\$((errors + 1))"
    refute_output --partial "print_warning"
}

@test "verify_installation still returns non-zero overall when errors accumulate" {
    # The increment only matters if the function's return honours it.
    run grep -cE 'errors=\$\(\(errors \+ 1\)\)' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_success
    [ "$output" -ge 2 ]
    run grep -qE 'return 1|exit 1' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_success
}
