#!/usr/bin/env bats
# Tests for bootstrap/lib/deploy.sh restore_runtime_state — the "Backup and
# replace" path must preserve user/runtime state (plugins, sessions, the user's
# own settings.json, …) instead of orphaning it into the backup directory.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_runtime.XXXXXX")
    # print_* helpers used by the function under test.
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # A minimal "repo-owned" source tree: these names get redeployed and so must
    # be EXCLUDED from the restore.
    SRC="$SANDBOX/configs/claude"
    mkdir -p "$SRC/config" "$SRC/scripts" "$SRC/.plans"
    echo "owned" > "$SRC/CLAUDE.md"

    # A backup that mimics a real live ~/.claude moved aside by `mv`: it holds
    # both repo-owned config AND runtime state.
    BK="$SANDBOX/.claude.backup"
    mkdir -p "$BK/config" "$BK/plugins/cache/mkt/remember/0.7.3" \
             "$BK/projects" "$BK/.remember" "$BK/.plans"
    echo "stale-owned"     > "$BK/CLAUDE.md"
    echo "user-settings"   > "$BK/settings.json"
    echo "plugin-state"    > "$BK/plugins/installed_plugins.json"
    echo "session"         > "$BK/projects/session.jsonl"
    echo "remember-data"   > "$BK/.remember/notes.md"

    TGT="$SANDBOX/home/.claude"
    mkdir -p "$TGT"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "restore_runtime_state restores plugins and sessions from backup" {
    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ -f "$TGT/plugins/installed_plugins.json" ]
    [ -d "$TGT/plugins/cache/mkt/remember/0.7.3" ]
    [ -f "$TGT/projects/session.jsonl" ]
    assert_equal "$(cat "$TGT/plugins/installed_plugins.json")" "plugin-state"
}

@test "restore_runtime_state restores the user's own settings.json and plugin data dirs" {
    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ -f "$TGT/settings.json" ]            # not repo-owned → preserved
    [ -f "$TGT/.remember/notes.md" ]       # plugin runtime data → preserved
    assert_equal "$(cat "$TGT/settings.json")" "user-settings"
}

@test "restore_runtime_state does NOT restore repo-owned config (redeploy wins)" {
    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    # Repo-owned entries are excluded so the fresh deploy is authoritative.
    [ ! -e "$TGT/CLAUDE.md" ]
    [ ! -e "$TGT/config" ]
    [ ! -e "$TGT/.plans" ]
}

@test "restore_runtime_state is a no-op success when backup dir is absent" {
    run restore_runtime_state "$SANDBOX/nonexistent" "$TGT" "$SRC"
    assert_success
    # Nothing created in the target.
    run find "$TGT" -mindepth 1
    assert_output ""
}

@test "restore_runtime_state handles a source with no dotfiles (unmatched glob)" {
    # source_dir with ONLY regular entries — the `.[!.]*` glob matches nothing
    # and must not abort or wrongly restore a literal '.[!.]*' name.
    local src2="$SANDBOX/src_nodot"
    mkdir -p "$src2/config"
    echo owned > "$src2/CLAUDE.md"

    run restore_runtime_state "$BK" "$TGT" "$src2"
    assert_success

    [ -f "$TGT/plugins/installed_plugins.json" ]   # runtime restored
    [ ! -e "$TGT/config" ]                          # owned still excluded
    [ ! -e "$TGT/.[!.]*" ]                          # no literal-glob junk file
}

@test "restore_runtime_state excludes a repo-owned 'skills' compat symlink" {
    # configs/claude/skills is a (possibly broken) symlink; it must be excluded
    # so rsync -a does not copy a dangling link from the backup into target.
    ln -s "../../.skillshare/skills" "$SRC/skills"   # broken on purpose
    mkdir -p "$BK/skills/should-not-restore"
    echo x > "$BK/skills/should-not-restore/SKILL.md"

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ ! -e "$TGT/skills" ]                           # backup skills NOT restored
    [ -f "$TGT/plugins/installed_plugins.json" ]     # runtime still restored
}

@test "restore_runtime_state preserves runtime dirs whose name matches a top-level owned name" {
    # Leading-'/' anchoring must only drop TOP-LEVEL owned entries, never a
    # nested path like plugins/config/ that happens to share the name 'config'.
    mkdir -p "$BK/plugins/config"
    echo nested > "$BK/plugins/config/data.json"

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ -f "$TGT/plugins/config/data.json" ]           # nested 'config' survives
    [ ! -e "$TGT/config" ]                            # top-level 'config' dropped
}
