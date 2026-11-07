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
printf '%s\n' "$*" >> "$UV_LOG"
printf '{"state":"READY"}\n'
STUB
    chmod +x "$HOME/.local/bin/uv"
    # Direct consumer tests establish the same invocation-scoped capability
    # that check_uv provides to production bootstrap.
    export MANIFEST_VERIFIED_UV_BIN="$HOME/.local/bin/uv"

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

@test "Codex native sync advances existing installation receipt via manifest update before bootstrap-sync" {
    mkdir -p "$HOME/.local/state/manifest"
    printf '{"schema_version":1}\n' > "$HOME/.local/state/manifest/installation.json"

    run sync_native_plugins

    assert_success
    assert_equal "$(sed -n '1p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest update --source $REPO_ROOT --non-interactive --json"
    assert_equal "$(sed -n '2p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest bootstrap-sync --source $REPO_ROOT --harness codex --non-interactive --json"
}

@test "Codex native sync honors XDG_STATE_HOME when checking for an installation receipt" {
    export XDG_STATE_HOME="$SANDBOX/xdg-state"
    mkdir -p "$XDG_STATE_HOME/manifest"
    printf '{"schema_version":1}\n' > "$XDG_STATE_HOME/manifest/installation.json"

    run sync_native_plugins

    assert_success
    assert_equal "$(sed -n '1p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest update --source $REPO_ROOT --non-interactive --json"
    assert_equal "$(sed -n '2p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest bootstrap-sync --source $REPO_ROOT --harness codex --non-interactive --json"
}

@test "sync_all_native_harnesses advances existing receipt when Codex is disabled" {
    export ENABLE_CODEX=false
    mkdir -p "$HOME/.local/state/manifest"
    printf '{"schema_version":1}\n' > "$HOME/.local/state/manifest/installation.json"

    run sync_native_plugins
    assert_success
    assert_equal "$( [[ -f "$UV_LOG" ]] && echo present || echo absent )" "absent"

    sync_all_native_harnesses > /dev/null
    assert_equal "$(sed -n '1p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest update --source $REPO_ROOT --non-interactive --json"
    assert_equal "$(sed -n '2p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest install --source $REPO_ROOT --non-interactive --json"
}

@test "sync_all_native_harnesses advances existing receipt when Codex CLI is absent" {
    rm -f "$SANDBOX/bin/codex"
    mkdir -p "$HOME/.local/state/manifest"
    printf '{"schema_version":1}\n' > "$HOME/.local/state/manifest/installation.json"

    run sync_native_plugins
    assert_success
    assert_equal "$( [[ -f "$UV_LOG" ]] && echo present || echo absent )" "absent"

    sync_all_native_harnesses > /dev/null
    assert_equal "$(sed -n '1p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest update --source $REPO_ROOT --non-interactive --json"
    assert_equal "$(sed -n '2p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest install --source $REPO_ROOT --non-interactive --json"
}

@test "deploy sequence updates existing receipt once across sync_native_plugins and sync_all_native_harnesses" {
    mkdir -p "$HOME/.local/state/manifest"
    printf '{"schema_version":1}\n' > "$HOME/.local/state/manifest/installation.json"

    sync_native_plugins > /dev/null
    sync_all_native_harnesses > /dev/null

    assert_equal "$(wc -l < "$UV_LOG" | tr -d ' ')" "3"
    assert_equal "$(sed -n '1p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest update --source $REPO_ROOT --non-interactive --json"
    assert_equal "$(sed -n '2p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest bootstrap-sync --source $REPO_ROOT --harness codex --non-interactive --json"
    assert_equal "$(sed -n '3p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest install --source $REPO_ROOT --non-interactive --json"
}

@test "sync_all_native_harnesses ignores uv stderr chatter and clears fallback native_harnesses state after per-harness parse" {
    mkdir -p "$HOME/.local/state/manifest"
    printf '{"schema_version":1}\n' > "$HOME/.local/state/manifest/installation.json"
    cat > "$HOME/.local/bin/uv" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" >> "$UV_LOG"
case "$*" in
    *"manifest update"*)
        printf 'update failed before report\n' >&2
        exit 1
        ;;
    *"manifest install"*)
        printf 'Resolved 5 packages in 12ms\n' >&2
        printf '{"operation":"install","state":"READY","harnesses":{"claude":{"state":"READY"}}}\n'
        exit 0
        ;;
esac
STUB
    chmod +x "$HOME/.local/bin/uv"

    sync_all_native_harnesses > "$SANDBOX/install.out" 2> "$SANDBOX/install.err"
    run cat "$SANDBOX/install.out"
    refute_output --partial "unreadable JSON"
    assert_output --partial "Manifest bundles installed natively in every detected harness"

    run _collect_degraded_harness_states
    assert_success
    assert_output ""
}

@test "failed codex bootstrap-sync stays degraded after a later plain install reports codex READY" {
    printf 'blocked\n' > "$SANDBOX/bootstrap.mode"
    cat > "$HOME/.local/bin/uv" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" >> "$UV_LOG"
case "$*" in
    *"manifest bootstrap-sync"*)
        if [ "$(cat "$SANDBOX_MODE_FILE")" = blocked ]; then
            printf '{"operation":"bootstrap-sync","state":"BLOCKED","harnesses":{"codex":{"state":"BLOCKED"}}}\n'
            exit 0
        fi
        printf '{"operation":"bootstrap-sync","state":"READY","harnesses":{"codex":{"state":"READY"}}}\n'
        ;;
    *"manifest install"*)
        printf '{"operation":"install","state":"READY","harnesses":{"codex":{"state":"READY"}}}\n'
        ;;
    *)
        printf '{"state":"READY"}\n'
        ;;
esac
STUB
    export SANDBOX_MODE_FILE="$SANDBOX/bootstrap.mode"

    local rc=0
    sync_native_plugins > /dev/null || rc=$?
    assert_equal "$rc" "1"
    sync_all_native_harnesses > /dev/null

    assert_equal "$MANIFEST_HARNESS_STATES" $'codex_bootstrap=BLOCKED\ncodex=READY'
    run _collect_degraded_harness_states
    assert_success
    assert_output "codex_bootstrap=BLOCKED"

    printf 'ready\n' > "$SANDBOX/bootstrap.mode"
    sync_native_plugins > /dev/null
    run _collect_degraded_harness_states
    assert_success
    assert_output ""
}

@test "receipt advance is skipped while a bootstrap-sync journal is pending" {
    mkdir -p "$HOME/.local/state/manifest"
    printf '{"schema_version":1}\n' > "$HOME/.local/state/manifest/installation.json"
    printf '{"phase":"pending"}\n' > "$HOME/.local/state/manifest/.installation.json.bootstrap-sync.json"

    run sync_native_plugins

    assert_success
    assert_output --partial "bootstrap-sync must recover first"
    assert_equal "$(wc -l < "$UV_LOG" | tr -d ' ')" "1"
    assert_equal "$(sed -n '1p' "$UV_LOG")" \
        "run --project $REPO_ROOT manifest bootstrap-sync --source $REPO_ROOT --harness codex --non-interactive --json"
}

@test "report parser preserves top-level failures when harness rows are READY" {
    unset MANIFEST_HARNESS_STATES XDG_STATE_HOME
    _record_manifest_report_states native_harnesses 0 \
        '{"operation":"install","state":"BLOCKED","errors":["receipt write failed"],"harnesses":{"claude":{"state":"READY"}}}'
    assert_equal "$MANIFEST_HARNESS_STATES" $'claude=READY\nnative_harnesses=BLOCKED'
    run _collect_degraded_harness_states
    assert_success
    assert_output "native_harnesses=BLOCKED"

    _record_manifest_report_states native_harnesses 1 \
        '{"operation":"install","state":"READY","errors":[],"harnesses":{"claude":{"state":"READY"}}}'
    assert_equal "$MANIFEST_HARNESS_STATES" $'claude=READY\nnative_harnesses=BLOCKED'
    run _collect_degraded_harness_states
    assert_success
    assert_output "native_harnesses=BLOCKED"
}

@test "repository-local Manifest runtime state is ignored" {
    run git -C "$REPO_ROOT" check-ignore \
        manifest/ownership.key \
        manifest/ownership.lock \
        manifest/skill-run-recovery/recovery.json

    assert_success
}
