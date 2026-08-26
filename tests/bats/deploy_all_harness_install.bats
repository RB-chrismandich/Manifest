#!/usr/bin/env bats

# Guards sync_all_native_harnesses: the deploy step that installs the Manifest
# bundles into every harness whose CLI is present. Its two load-bearing
# properties are the flagless invocation (see the function's comment: naming
# `--harness all` inverts absent-CLI handling from note to error) and its
# non-fatal contract.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_all_harness.XXXXXX")
    export HOME="$SANDBOX/home"
    export SCRIPT_DIR="$REPO_ROOT"
    export UV_LOG="$SANDBOX/uv.log"
    export UV_STATE=READY
    export UV_RC=0
    mkdir -p "$HOME/.local/bin" "$SANDBOX/bin"

    cat > "$HOME/.local/bin/uv" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" > "$UV_LOG"
[ "$UV_RC" -ne 0 ] && { printf 'native refusal\n'; exit "$UV_RC"; }
printf '{"state":"%s"}\n' "$UV_STATE"
STUB
    chmod +x "$HOME/.local/bin/uv"

    export PATH="$SANDBOX/bin:/usr/bin:/bin"
    export RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "all-harness install omits --harness so absent CLIs stay notes" {
    run sync_all_native_harnesses

    assert_success
    assert_equal "$(cat "$UV_LOG")" \
        "run --project $REPO_ROOT manifest install --source $REPO_ROOT --non-interactive --json"
    refute_output --partial "--harness"
}

@test "a refusing harness never fails the deploy" {
    export UV_RC=1

    run sync_all_native_harnesses

    assert_success
    assert_output --partial "native refusal"
}

@test "a non-READY state is reported, not swallowed" {
    export UV_STATE=DEGRADED

    run sync_all_native_harnesses

    assert_success
    assert_output --partial "DEGRADED"
}

@test "missing uv skips without failing the deploy" {
    rm -f "$HOME/.local/bin/uv"

    run sync_all_native_harnesses

    assert_success
    assert_output --partial "uv not available"
    [[ ! -f "$UV_LOG" ]]
}
