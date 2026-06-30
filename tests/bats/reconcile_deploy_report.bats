#!/usr/bin/env bats
# US2 — deploy-time reconcile report (feature 368): report-only + fail-open.
# Covers reconcile_deploy_report() in bootstrap/lib/deploy.sh.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/reconcile_deploy.XXXXXX")
    export HOME="$SANDBOX/home"          # fixture home — never touch the real ~/.claude
    export MANIFEST_STATE_ROOT="$SANDBOX/state"
    mkdir -p "$HOME/.claude/skills/dead" "$HOME/.claude/config"
    echo "x" > "$HOME/.claude/skills/dead/SKILL.md"
    echo "stale" > "$HOME/.claude/config/old_layout.yml"
    # source the libs under test (functions only)
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "reconcile_deploy_report is report-only: prints a summary, returns 0, creates no backup" {
    SCRIPT_DIR="$REPO_ROOT"
    run reconcile_deploy_report
    assert_success
    assert_output --partial "Summary:"
    # report-only: no removal backup may be created
    [ ! -d "$MANIFEST_STATE_ROOT/reconcile-trash" ]
    # orphan must still be present on disk (nothing deleted)
    [ -d "$HOME/.claude/skills/dead" ]
}

@test "reconcile_deploy_report is fail-open: returns 0 even when the review errors" {
    # Point SCRIPT_DIR at a fake repo whose deploy_reconcile.sh exits nonzero.
    SCRIPT_DIR="$SANDBOX/fakerepo"
    mkdir -p "$SCRIPT_DIR/configs/claude/scripts"
    printf '#!/usr/bin/env bash\necho boom >&2\nexit 1\n' > "$SCRIPT_DIR/configs/claude/scripts/deploy_reconcile.sh"
    chmod +x "$SCRIPT_DIR/configs/claude/scripts/deploy_reconcile.sh"
    run reconcile_deploy_report
    assert_success                       # never aborts the deploy
}

@test "reconcile_deploy_report no-ops cleanly when the script is absent" {
    SCRIPT_DIR="$SANDBOX/empty"
    mkdir -p "$SCRIPT_DIR"
    run reconcile_deploy_report
    assert_success
}
