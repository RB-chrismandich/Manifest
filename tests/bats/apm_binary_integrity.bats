#!/usr/bin/env bats
# T054/FR-029: `apm` binary acquisition and integrity verification in bootstrap.
#
# Distinct from apm_install_verify.bats (T050/FR-018), which verifies *packages*
# at install time. This verifies the *tool doing the installing*: apm writes
# hooks and MCP server definitions into five home trees, so its own install
# channel is code execution, not inert configuration.
#
# The load-bearing property is FAIL CLOSED. Unlike install_graphify (an optional
# capability that warns and continues), every failure path here must refuse to
# install — an unverified apm binary is worse than no apm binary. "Indeterminate"
# counts as a failure: if we cannot compute a checksum, we do not install.
#
# Nothing here touches the network, the real $HOME, or a real uv installation;
# every collaborator is a stub that records its arguments so the tests can assert
# on what was *not* called.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_binary_integrity.XXXXXX")"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/install.sh"

    # Quiet the output helpers but keep errors greppable via $output.
    print_step() { echo "STEP: $*"; }
    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    print_warning() { echo "WARN: $*"; }
    print_error() { echo "ERROR: $*"; }

    # Call log — tests assert on what was and was not invoked.
    CALLS="$SANDBOX/calls.log"
    : > "$CALLS"

    ENABLE_APM=true

    # A stub uv that records every invocation. `uv tool list` reports nothing
    # installed unless a test overrides UV_TOOL_LIST_OUT.
    UV_TOOL_LIST_OUT=""
    uv() {
        echo "uv $*" >> "$CALLS"
        if [[ "$1" == "tool" && "$2" == "list" ]]; then
            printf '%s\n' "$UV_TOOL_LIST_OUT"
            return 0
        fi
        return "${UV_EXIT:-0}"
    }
    command_exists() { [[ "$1" == "uv" ]]; }

    # Default seams: resolution and download succeed, producing known bytes.
    WHEEL_BODY="pretend wheel bytes"
    apm_resolve_wheel_url() {
        echo "resolve" >> "$CALLS"
        echo "https://example.invalid/apm_cli-0.26.0-py3-none-any.whl"
    }
    apm_download() {
        echo "download $1 -> $2" >> "$CALLS"
        printf '%s' "$WHEEL_BODY" > "$2"
    }

    # Pin the expected digest to whatever the stub body actually hashes to, so
    # the happy path is genuinely a match rather than a disabled check.
    GOOD_SHA="$(printf '%s' "$WHEEL_BODY" | shasum -a 256 | awk '{print $1}')"
    APM_WHEEL_SHA256="$GOOD_SHA"
    APM_PINNED_VERSION="0.26.0"

    # Stub the *binary location*, not the probe. apm_installed_version stays
    # real in every test, so its $HOME redirection is exercised throughout
    # rather than only in the one test that names it.
    #
    # The fake binary mimics the two behaviours that matter: it prints a
    # version banner in apm's format, and it writes into $HOME the way apm
    # does (T001 finding 4 — `apm --help` alone creates ~/.apm/config.json).
    export PROBE_VERSION="${PROBE_VERSION:-0.26.0}"
    cat > "$SANDBOX/fake-apm" << 'SH'
#!/usr/bin/env bash
mkdir -p "$HOME/.apm" && echo '{}' > "$HOME/.apm/config.json"
echo "Agent Package Manager (APM) CLI version ${PROBE_VERSION:-0.26.0}"
SH
    chmod +x "$SANDBOX/fake-apm"
    apm_binary() { echo "$SANDBOX/fake-apm"; }
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# --- fail-closed paths -------------------------------------------------------

@test "checksum mismatch refuses to install" {
    APM_WHEEL_SHA256="0000000000000000000000000000000000000000000000000000000000000000"

    run install_apm_cli
    assert_failure
    assert_output --partial "checksum"
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}

@test "checksum is verified BEFORE the installer ever runs" {
    # Ordering matters: verifying after installing protects nothing. Assert the
    # install call is absent entirely, not merely that the function failed.
    APM_WHEEL_SHA256="0000000000000000000000000000000000000000000000000000000000000000"

    run install_apm_cli
    assert_failure
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}

@test "download failure refuses to install (no unverified fallback)" {
    apm_download() {
        echo "download-failed" >> "$CALLS"
        return 1
    }

    run install_apm_cli
    assert_failure
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}

@test "URL resolution failure refuses to install" {
    apm_resolve_wheel_url() { return 1; }

    run install_apm_cli
    assert_failure
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}

@test "an unusable checksum tool is treated as failure, not as a pass" {
    # Indeterminate must fail closed. An empty digest compared against a pin
    # must never satisfy the check.
    apm_sha256() { echo ""; }

    run install_apm_cli
    assert_failure
    run cat "$CALLS"
    refute_output --partial "uv tool install"
}

@test "a post-install version mismatch is a failure" {
    # uv reported success, but the binary that landed is not the pinned one.
    # Trusting the installer's exit code alone would accept it.
    export PROBE_VERSION="0.25.0"

    run install_apm_cli
    assert_failure
    assert_output --partial "0.25.0"
}

# --- happy path --------------------------------------------------------------

@test "matching checksum installs the tool" {
    run install_apm_cli
    assert_success
    run cat "$CALLS"
    assert_output --partial "uv tool install"
}

@test "installs the verified local file, not a re-resolved remote package" {
    # The subtle correctness property: verifying bytes and then asking the
    # package manager to fetch the name again discards the verification.
    run install_apm_cli
    assert_success

    run grep "uv tool install" "$CALLS"
    assert_output --partial ".whl"
    refute_output --partial "apm-cli=="
    refute_output --partial "https://"
}

# --- guards ------------------------------------------------------------------

@test "disabled by default: no download, no install" {
    ENABLE_APM=false

    run install_apm_cli
    assert_success
    run cat "$CALLS"
    refute_output --partial "download"
    refute_output --partial "uv tool install"
}

@test "idempotent: already installed at the pinned version does not re-download" {
    UV_TOOL_LIST_OUT="apm-cli v0.26.0"

    run install_apm_cli
    assert_success
    run cat "$CALLS"
    refute_output --partial "download"
}

@test "a different installed version is replaced, not left in place" {
    UV_TOOL_LIST_OUT="apm-cli v0.25.0"

    run install_apm_cli
    assert_success
    run cat "$CALLS"
    assert_output --partial "uv tool install"
}

# --- side-effect containment -------------------------------------------------

@test "the version probe does not create ~/.apm in the real HOME" {
    # T001 finding 4: `apm --help` alone creates ~/.apm/config.json. Probing the
    # freshly installed binary must not be what provisions a user's home.
    FAKE_HOME="$SANDBOX/home"
    mkdir -p "$FAKE_HOME"
    HOME="$FAKE_HOME"

    run install_apm_cli
    assert_success
    [ ! -e "$FAKE_HOME/.apm" ]

    # Control: the fake binary provably DOES write $HOME/.apm when run without
    # the redirection. Without this, the assertion above would also pass if the
    # probe had never run the binary at all.
    run env HOME="$FAKE_HOME" "$SANDBOX/fake-apm"
    assert_success
    [ -e "$FAKE_HOME/.apm" ]
}
