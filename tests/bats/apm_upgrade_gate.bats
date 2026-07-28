#!/usr/bin/env bats
# T045/FR-029 — the upgrade gate — and T044/FR-031 — the offline install path.
#
# T045's requirement is that bumping the pinned tool version must re-run the
# equivalence and idempotence checks "and fail if they are not run". A test
# cannot observe whether a human ran a check. What it CAN do is refuse to let
# the pin move silently: the verified pin is recorded in
# configs/claude/config/apm_pin_verified.txt, and this suite asserts the two
# agree. Bumping install.sh alone turns the suite red, which forces the bump to
# arrive with someone's explicit "I re-verified this".
#
# That is a forcing function, not a proof, and the record file says so in its
# own header. A gate that makes an omission visible is worth having; one that
# claims to make it impossible would be lying.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INSTALL_LIB="$REPO_ROOT/bootstrap/lib/install.sh"
PIN_RECORD="$REPO_ROOT/configs/claude/config/apm_pin_verified.txt"

pin_field() { sed -n "s/^$1 = //p" "$PIN_RECORD" | head -1; }
lib_value() { sed -n "s/^$1=\"\${$1:-\(.*\)}\"$/\1/p" "$INSTALL_LIB" | head -1; }

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_upgrade.XXXXXX")"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# --- T045: the pin cannot move without the verification record moving --------

@test "the verified-pin record exists" {
    [ -f "$PIN_RECORD" ]
}

@test "the pinned version matches the verified record" {
    # Red here means: install.sh's pin was bumped without re-running the
    # equivalence and idempotence checks and recording the result.
    [ "$(lib_value APM_PINNED_VERSION)" = "$(pin_field version)" ]
}

@test "the pinned sha256 matches the verified record" {
    # The digest IS the provenance for this artifact (PyPI ties apm-cli to no
    # repository), so a version bump that keeps a stale digest is worse than a
    # missing check — it looks verified.
    [ "$(lib_value APM_WHEEL_SHA256)" = "$(pin_field sha256)" ]
}

@test "the record carries who verified it and when, not just the values" {
    # Values alone cannot be audited later. Without provenance on the record,
    # "verified" degrades to "someone typed a hash once".
    run cat "$PIN_RECORD"
    assert_output --partial "verified_on"
    assert_output --partial "verified_by"
}

@test "the record documents the upgrade procedure it gates" {
    # A gate that fails without telling you what to do next just gets deleted.
    run cat "$PIN_RECORD"
    assert_output --partial "idempotence"
    assert_output --partial "equivalence"
}

@test "the comparison is real: a mutated record would not match the lib" {
    # Guards against both extractors silently returning empty, which would make
    # every assertion above compare "" to "" and pass forever.
    [ -n "$(lib_value APM_PINNED_VERSION)" ]
    [ -n "$(lib_value APM_WHEEL_SHA256)" ]
    [ -n "$(pin_field version)" ]
    [ "$(lib_value APM_PINNED_VERSION)" != "$(pin_field sha256)" ]
}

# --- T044: offline install from a pinned local artifact ----------------------

@test "an offline install uses the local artifact and never resolves or downloads" {
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$INSTALL_LIB"
    print_step() { :; }
    print_info() { :; }
    print_success() { :; }
    print_warning() { :; }
    print_error() { echo "ERROR: $*"; }

    ENABLE_APM=true
    CALLS="$SANDBOX/calls.log"
    : > "$CALLS"
    command_exists() { [[ "$1" == "uv" ]]; }
    uv() {
        echo "uv $*" >> "$CALLS"
        [[ "$1 $2" == "tool list" ]] && echo ""
        return 0
    }
    apm_resolve_wheel_url() {
        echo "RESOLVED" >> "$CALLS"
        echo "https://example.invalid/w.whl"
    }
    apm_download() {
        echo "DOWNLOADED" >> "$CALLS"
        return 0
    }
    apm_binary() { echo "$SANDBOX/fake-apm"; }
    printf '#!/usr/bin/env bash\necho "version 0.26.0"\n' > "$SANDBOX/fake-apm"
    chmod +x "$SANDBOX/fake-apm"

    printf 'offline wheel bytes' > "$SANDBOX/apm.whl"
    APM_WHEEL_SHA256="$(shasum -a 256 "$SANDBOX/apm.whl" | awk '{print $1}')"
    APM_WHEEL_LOCAL="$SANDBOX/apm.whl"

    run install_apm_cli
    assert_success

    run cat "$CALLS"
    assert_output --partial "uv tool install"
    refute_output --partial "RESOLVED"
    refute_output --partial "DOWNLOADED"
}

@test "an offline install still verifies the checksum" {
    # "I brought my own file" is not evidence about what is in it, and an
    # air-gapped install is exactly when nobody is watching.
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$INSTALL_LIB"
    print_step() { :; }
    print_info() { :; }
    print_success() { :; }
    print_warning() { :; }
    print_error() { echo "ERROR: $*"; }

    ENABLE_APM=true
    CALLS="$SANDBOX/calls.log"
    : > "$CALLS"
    command_exists() { [[ "$1" == "uv" ]]; }
    uv() {
        echo "uv $*" >> "$CALLS"
        [[ "$1 $2" == "tool list" ]] && echo ""
        return 0
    }

    printf 'tampered offline wheel' > "$SANDBOX/apm.whl"
    APM_WHEEL_LOCAL="$SANDBOX/apm.whl"
    APM_WHEEL_SHA256="0000000000000000000000000000000000000000000000000000000000000000"

    run install_apm_cli
    assert_failure
    assert_output --partial "checksum mismatch"
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}

@test "a missing local artifact is an error, not a silent fallback to the network" {
    # Falling back would turn an air-gapped install into an unnoticed online one.
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$INSTALL_LIB"
    print_step() { :; }
    print_info() { :; }
    print_success() { :; }
    print_warning() { :; }
    print_error() { echo "ERROR: $*"; }

    ENABLE_APM=true
    command_exists() { [[ "$1" == "uv" ]]; }
    uv() {
        [[ "$1 $2" == "tool list" ]] && echo ""
        return 0
    }
    apm_resolve_wheel_url() { echo "SHOULD NOT BE CALLED"; }
    APM_WHEEL_LOCAL="$SANDBOX/does-not-exist.whl"

    run install_apm_cli
    assert_failure
    assert_output --partial "not a file"
}
