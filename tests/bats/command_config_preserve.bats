#!/usr/bin/env bats
# preserve_issue_sync_gates(): opt-in issue-sync gates flipped to enabled: true
# in the DEPLOYED ~/.claude/config/command_config.yml (by install_issue_hooks.sh)
# must survive a bootstrap redeploy, which overwrites the file with the repo
# default (enabled: false). Scope: ONLY the two hooks' enabled: values — the
# repo copy stays authoritative for everything else (issue #461).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    TMPDIR_T="$(mktemp -d)"
    PRESERVED="$TMPDIR_T/preserved.yml" # snapshot of live command_config.yml
    TGT="$TMPDIR_T/tgt.yml"             # freshly deployed repo copy

    command_exists() { command -v "$1" > /dev/null 2>&1; }
    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    print_warning() { echo "WARN: $*"; }
    export -f command_exists print_info print_success print_warning 2> /dev/null || true

    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh" 2> /dev/null || true

    # Repo-shipped default shape (comments intact, gates false)
    cat > "$TGT" <<'YML'
tool_policies:
  issue-sync-pr:
    # hook-triggered; opt-in via install_issue_hooks.sh
    enabled: false
    allowed:
      - Bash
  issue-sync-commit:
    enabled: false
    allowed:
      - Bash
  other-skill:
    enabled: false
YML
}

teardown() {
    rm -rf "$TMPDIR_T"
}

_live_optin() { # snapshot where the user opted in to both hooks
    cat > "$PRESERVED" <<'YML'
tool_policies:
  issue-sync-pr:
    # hook-triggered; opt-in via install_issue_hooks.sh
    enabled: true
    allowed:
      - Bash
  issue-sync-commit:
    enabled: true
    allowed:
      - Bash
  other-skill:
    enabled: true
YML
}

@test "opted-in gates survive a redeploy (true carried over false)" {
    _live_optin
    run preserve_issue_sync_gates "$PRESERVED" "$TGT"
    assert_success
    grep -A3 '^  issue-sync-pr:' "$TGT" | grep -q 'enabled: true'
    grep -A2 '^  issue-sync-commit:' "$TGT" | grep -q 'enabled: true'
}

@test "scope guard: other skills' gates are NOT carried over" {
    _live_optin
    run preserve_issue_sync_gates "$PRESERVED" "$TGT"
    assert_success
    grep -A2 '^  other-skill:' "$TGT" | grep -q 'enabled: false'
}

@test "comments in the target survive the rewrite" {
    _live_optin
    run preserve_issue_sync_gates "$PRESERVED" "$TGT"
    assert_success
    grep -q 'hook-triggered; opt-in via install_issue_hooks.sh' "$TGT"
}

@test "fresh install (no snapshot) leaves repo defaults untouched" {
    run preserve_issue_sync_gates "" "$TGT"
    assert_success
    grep -A3 '^  issue-sync-pr:' "$TGT" | grep -q 'enabled: false'
}

@test "snapshot with gates still false changes nothing" {
    cp "$TGT" "$PRESERVED"
    before=$(cat "$TGT")
    run preserve_issue_sync_gates "$PRESERVED" "$TGT"
    assert_success
    assert_output --partial "No issue-sync opt-in gates"
    [ "$(cat "$TGT")" = "$before" ]
}

@test "deploy_configs snapshots command_config.yml before the copy paths" {
    # wiring assertion: the snapshot + both preserve call sites exist
    grep -q 'preserved_cmdcfg' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    [ "$(grep -c 'preserve_issue_sync_gates "\$preserved_cmdcfg"' "$REPO_ROOT/bootstrap/lib/deploy.sh")" -ge 2 ]
}
