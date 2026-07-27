#!/usr/bin/env bats
# T042/FR-018/FR-029 — the supply-chain gates are regression-proof.
#
# The four gates already have their own suites, which test them WORKING. This
# file tests the one property those suites do not assert as a set: that each
# gate FAILS CLOSED when its subject is invalid. FR-018 was the single
# cross-cutting invariant with no enforcing test, and a gate that quietly
# degrades to "warn and continue" still passes every happy-path suite.
#
# The four subjects, and what invalid means for each:
#
#   T048 pre-publish scan       — a secret in the tree must BLOCK the publish
#   T049 provenance gate        — a dirty tree or an untagged HEAD must block
#   T050 package integrity      — bytes not matching the gate record must block
#   T054 binary integrity       — a wheel not matching the pinned sha256 must
#                                 leave apm uninstalled
#
# "Indeterminate" counts as invalid throughout: a gate that cannot positively
# validate its subject must reject it, never pass it through.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'
load '../test_helper/git_fixture'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
GATE="$REPO_ROOT/configs/claude/scripts/apm_publish_gate.sh"
VERIFY="$REPO_ROOT/configs/claude/scripts/apm_install_verify.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_supply.XXXXXX")"
    git_fixture_env

    REPO="$SANDBOX/repo"
    mkdir -p "$REPO"
    git -C "$REPO" init -q -b main
    git -C "$REPO" commit -q --allow-empty -m init
    git -C "$REPO" tag v1.0.0

    PKG="$SANDBOX/pkg"
    mkdir -p "$PKG"
    echo "an ordinary primitive" > "$PKG/skill.md"

    export APM_GATE_RECORD_FILE="$SANDBOX/gate-records.jsonl"
    export APM_GATE_REPO="$REPO"
}

teardown() {
    git_fixture_unset
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Plant a secret the repo's OWN gitleaks config detects (rule: aws-access-key,
# AKIA + 16 uppercase alphanumerics). Built by concatenation at run time on
# purpose: a literal secret-shaped string in this file would trip the repo's own
# pre-commit scanner, so the test that proves the scanner works could not itself
# be committed.
plant_detectable_secret() {
    printf 'key = "%s%s"\n' "AKIA" "ABCDEFGHIJKLMNOP" > "$PKG/leak.txt"
}

# --- T048: the content scan blocks rather than warns --------------------------

@test "T048 fails closed on a secret in the published tree" {
    plant_detectable_secret

    run "$GATE" scan "$PKG"
    assert_failure
}

@test "T048 fails closed when the scanner itself is unavailable" {
    # Gitleaks absent must REJECT, never silently degrade to the weaker
    # in-script regex pass. A scan that cannot run has not found nothing.
    stub="$SANDBOX/bin"
    mkdir -p "$stub"
    printf '#!/usr/bin/env bash\nexit 127\n' > "$stub/gitleaks"
    chmod +x "$stub/gitleaks"

    PATH="$stub:$PATH" run "$GATE" scan "$PKG"
    assert_failure
}

@test "T048 passes a clean tree, so the failures above are not vacuous" {
    run "$GATE" scan "$PKG"
    assert_success
}

# --- T049: provenance ---------------------------------------------------------

@test "T049 fails closed on a dirty working tree" {
    echo "uncommitted" > "$REPO/dirty.txt"

    run "$GATE" provenance
    assert_failure
}

@test "T049 fails closed when HEAD is not at a tag" {
    git -C "$REPO" commit -q --allow-empty -m "past the tag"

    run "$GATE" provenance
    assert_failure
}

@test "T049 passes a clean tree at a tag" {
    run "$GATE" provenance
    assert_success
}

# --- T050: install-time package integrity ------------------------------------

@test "T050 fails closed when the fetched bytes do not match the gate record" {
    "$GATE" all "$PKG" > /dev/null
    # The attacker's tree: same name, different content.
    echo "tampered" >> "$PKG/skill.md"

    run "$VERIFY" verify "$PKG" --ref v1.0.0
    assert_failure
}

@test "T050 fails closed when no gate record exists for the requested ref" {
    # The typosquat/repo-reuse case: content nobody gated.
    run "$VERIFY" verify "$PKG" --ref v9.9.9
    assert_failure
}

@test "T050 passes the exact bytes that were gated" {
    "$GATE" all "$PKG" > /dev/null

    run "$VERIFY" verify "$PKG" --ref v1.0.0
    assert_success
}

# --- SC-011: every publish attempt leaves a record ---------------------------

@test "a REJECTED gate run still writes a record" {
    # SC-011 needs a record preceding every publish ATTEMPT, not only the
    # successful ones — otherwise the audit trail shows only the good days.
    plant_detectable_secret

    run "$GATE" all "$PKG"
    assert_failure
    run cat "$APM_GATE_RECORD_FILE"
    assert_output --partial '"result": "fail"'
}

# --- T054: the binary that does the installing -------------------------------

@test "T054 fails closed on a wheel that does not match the pinned digest" {
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/install.sh"
    print_step() { :; }
    print_info() { :; }
    print_success() { :; }
    print_error() { echo "ERROR: $*"; }
    print_warning() { :; }

    ENABLE_APM=true
    command_exists() { [[ "$1" == "uv" ]]; }
    CALLS="$SANDBOX/uv.log"
    : > "$CALLS"
    uv() {
        echo "uv $*" >> "$CALLS"
        [[ "$1 $2" == "tool list" ]] && echo ""
        return 0
    }
    apm_resolve_wheel_url() { echo "https://example.invalid/w.whl"; }
    apm_download() { printf 'not the pinned bytes' > "$2"; }
    APM_WHEEL_SHA256="0000000000000000000000000000000000000000000000000000000000000000"

    run install_apm_cli
    assert_failure
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}
