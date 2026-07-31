#!/usr/bin/env bats
# Drive the REAL deploy_configs() existing-install menu and gate the
# non-destructive "Update config" option (4).
#
# Why this exists: the menu offered only "Backup and replace" (destructive: mv
# the whole ~/.claude aside) and "Merge" (rsync --ignore-existing, which ONLY
# adds new paths). Editing an already-deployed repo-owned file and re-running
# bootstrap was therefore a silent no-op, and the only way to get the edit
# deployed was the destructive path — which is what stranded an operator with a
# half-restored home on 2026-07-30. Option 4 refreshes repo-owned files in place
# and never removes anything.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    # Isolate the APM domain registry for the same reason
    # deploy_runtime_state_e2e.bats does: ambient ~/.apm state must not decide
    # whether deploy_home_skills stands down mid-test.
    export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"

    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_update.XXXXXX")

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # Real repo configs are the deploy source; every home path is sandboxed.
    # NEVER let TARGET_DIR point at the real ~/.claude.
    export SCRIPT_DIR="$REPO_ROOT"
    export HOME="$SANDBOX/home"
    export TARGET_DIR="$HOME/.claude"
    export CURSOR_TARGET_DIR="$HOME/.cursor"
    export GEMINI_TARGET_DIR="$HOME/.gemini"
    export CODEX_TARGET_DIR="$HOME/.codex"
    export ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export MANIFEST_OUTPUT_DIR="$HOME/.manifest/outputs"
    export FORCE=false

    # Isolate heavy/secondary routines (network, profiles, other agents).
    write_services_config()      { :; }
    deploy_cursor_configs()      { :; }
    deploy_gemini_configs()      { :; }
    deploy_codex_configs()       { :; }
    deploy_antigravity_configs() { :; }
    deploy_sync_skills()         { :; }

    # A live ~/.claude holding runtime state plus a STALE copy of repo-owned
    # config. "Stale" is the whole point: option 2 leaves it stale, option 4
    # refreshes it.
    mkdir -p "$TARGET_DIR/plugins/cache/mkt/remember/0.7.3" \
             "$TARGET_DIR/projects" "$TARGET_DIR/.remember" "$TARGET_DIR/config"
    echo '{"plugins":{"remember":1}}' > "$TARGET_DIR/plugins/installed_plugins.json"
    echo 'session-data'               > "$TARGET_DIR/projects/abc.jsonl"
    echo 'user-private-settings'      > "$TARGET_DIR/settings.json"
    echo 'remember-notes'             > "$TARGET_DIR/.remember/notes.md"
    echo 'STALE-CLAUDE-MD'            > "$TARGET_DIR/CLAUDE.md"
    echo 'STALE-LABELS'               > "$TARGET_DIR/config/labels.yml"
    # User content that exists ONLY in the target — must never be deleted.
    echo 'keepme'                     > "$TARGET_DIR/my_personal_note.md"
    echo 'OLD'                        > "$TARGET_DIR/config/OLD_THING.yml"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# The deploy genuinely ran and refreshed repo-owned config in place. Anchoring
# every option-4 test on this keeps them from passing trivially when the menu
# falls through to Cancel and touches nothing.
assert_repo_config_refreshed() {
    run cmp -s "$TARGET_DIR/CLAUDE.md" "$REPO_ROOT/configs/claude/CLAUDE.md"
    assert_success
    run cmp -s "$TARGET_DIR/config/labels.yml" "$REPO_ROOT/configs/claude/config/labels.yml"
    assert_success
}

@test "option 4 updates a repo-owned file whose content changed (the case merge misses)" {
    deploy_configs <<< "4"
    assert_repo_config_refreshed
    # Prove it against the stale sentinel too, not just the cmp.
    run cat "$TARGET_DIR/CLAUDE.md"
    refute_output --partial "STALE-CLAUDE-MD"
}

@test "option 4 preserves unrelated runtime files that exist only in the target" {
    deploy_configs <<< "4"
    assert_repo_config_refreshed

    [ -f "$TARGET_DIR/plugins/installed_plugins.json" ]
    [ -d "$TARGET_DIR/plugins/cache/mkt/remember/0.7.3" ]
    [ -f "$TARGET_DIR/.remember/notes.md" ]
    assert_equal "$(cat "$TARGET_DIR/projects/abc.jsonl")" "session-data"
    assert_equal "$(cat "$TARGET_DIR/settings.json")" "user-private-settings"
}

@test "option 4 does not delete a user file absent from the source tree" {
    deploy_configs <<< "4"
    assert_repo_config_refreshed

    # Top level, and nested inside a repo-owned directory: no --delete anywhere.
    assert_equal "$(cat "$TARGET_DIR/my_personal_note.md")" "keepme"
    assert_equal "$(cat "$TARGET_DIR/config/OLD_THING.yml")" "OLD"
}

@test "option 4 leaves the live directory in place (no timestamped backup)" {
    deploy_configs <<< "4"
    assert_repo_config_refreshed

    run bash -c "ls -d '$HOME'/.claude.backup.* 2>/dev/null | wc -l | tr -d ' '"
    assert_output "0"
}

@test "option 2 still does NOT update an existing file (contract unchanged)" {
    deploy_configs <<< "2"

    # --ignore-existing: the stale copies stay stale. This is the documented
    # merge contract and the defect that motivated option 4 — not a bug to fix
    # here.
    assert_equal "$(cat "$TARGET_DIR/CLAUDE.md")" "STALE-CLAUDE-MD"
    assert_equal "$(cat "$TARGET_DIR/config/labels.yml")" "STALE-LABELS"
    # …but it does still add paths that were missing.
    [ -d "$TARGET_DIR/scripts" ]
}

@test "an invalid menu answer cancels and takes no destructive branch" {
    run deploy_configs <<< "banana"
    assert_success
    assert_output --partial "Installation cancelled"

    # Nothing moved aside, nothing refreshed, nothing removed.
    run bash -c "ls -d '$HOME'/.claude.backup.* 2>/dev/null | wc -l | tr -d ' '"
    assert_output "0"
    assert_equal "$(cat "$TARGET_DIR/CLAUDE.md")" "STALE-CLAUDE-MD"
    assert_equal "$(cat "$TARGET_DIR/my_personal_note.md")" "keepme"
    assert_equal "$(cat "$TARGET_DIR/settings.json")" "user-private-settings"
    [ ! -d "$TARGET_DIR/scripts" ]
}

@test "an empty menu answer cancels too" {
    run deploy_configs <<< ""
    assert_success
    assert_output --partial "Installation cancelled"
    assert_equal "$(cat "$TARGET_DIR/CLAUDE.md")" "STALE-CLAUDE-MD"
}

@test "the menu tells the truth about what each option does" {
    run deploy_configs <<< "3"
    assert_success
    # Option 2's honest label: it adds, it does not update. The old label
    # ("Merge (keep existing, add new)") let an operator read "merge" as
    # "reconcile my edits", which it never did.
    assert_output --partial "existing files are NOT updated"
    refute_output --partial "Merge (keep existing, add new)"
    # The new non-destructive option is advertised, and option 1 is marked.
    assert_output --partial "4. Update config"
    assert_output --partial "destructive"

    # bash suppresses a `read -p` prompt when stdin is not a tty, so the accepted
    # range never appears in captured output. Gate it at the source instead: a
    # prompt still reading [1/2/3] tells the operator 4 is invalid.
    run grep -c 'Choose option \[1/2/3/4\]: ' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_output "1"
}
