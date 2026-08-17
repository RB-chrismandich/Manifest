#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_codex_native.XXXXXX")
    export HOME="$SANDBOX/home"
    export SCRIPT_DIR="$REPO_ROOT"
    export ENABLE_CODEX=true
    export UV_LOG="$SANDBOX/uv.log"
    mkdir -p "$HOME/.local/bin" "$SANDBOX/bin"

    printf '#!/bin/sh\nexit 0\n' > "$SANDBOX/bin/codex"
    chmod +x "$SANDBOX/bin/codex"
    cat > "$HOME/.local/bin/uv" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" > "$UV_LOG"
printf '{"state":"READY"}\n'
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

@test "Codex native sync uses supported user-local uv outside PATH" {
    run sync_native_plugins

    assert_success
    assert_equal "$(cat "$UV_LOG")" \
        "run --project $REPO_ROOT manifest bootstrap-sync --source $REPO_ROOT --harness codex --non-interactive --json"
}

@test "repository-local Manifest runtime state is ignored" {
    run git -C "$REPO_ROOT" check-ignore \
        manifest/ownership.key \
        manifest/ownership.lock \
        manifest/skill-run-recovery/recovery.json

    assert_success
}
