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
    ln -s "../../.apm/skills" "$SRC/skills"   # broken on purpose
    mkdir -p "$BK/skills/should-not-restore"
    echo x > "$BK/skills/should-not-restore/SKILL.md"

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ ! -e "$TGT/skills" ]                           # backup skills NOT restored
    [ -f "$TGT/plugins/installed_plugins.json" ]     # runtime still restored
}

# --- foreign entries inside a repo-owned name ---------------------------------
#
# Excluding a top-level name from the restore is only safe while the deploy
# REDEPLOYS that name. Two of them no longer are:
#
#   skills/  — since the domain retired (SC-006/spec 674) deploy_home_skills
#              writes MANIFEST_SKILLS_DIR (~/.manifest/skills), never
#              $TARGET_DIR/skills, so nothing recreates the tree.
#   agents/  — gate_pilotfish_agents/gate_devpanel_agents deploy exactly their
#              own role files and are documented to let a coexisting
#              user-authored agent survive an opt-out.
#
# For both, a blanket exclude turns "the fresh deploy wins" into a silent
# delete of state that belongs to somebody else. Measured 2026-07-31: an
# option-1 rerun took ~/.claude/skills/.system (Codex's own installs —
# imagegen, openai-docs, plugin-creator, skill-creator, skill-installer) with
# it, and nothing put it back.

@test "restore_runtime_state restores foreign skill installs nothing redeploys (.system)" {
    ln -s "../../.apm/skills" "$SRC/skills"          # the compat symlink, as shipped
    mkdir -p "$BK/skills/.system/imagegen"
    echo "codex-owned" > "$BK/skills/.system/imagegen/SKILL.md"

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ -f "$TGT/skills/.system/imagegen/SKILL.md" ]
    assert_equal "$(cat "$TGT/skills/.system/imagegen/SKILL.md")" "codex-owned"
}

@test "restore_runtime_state still skips bytecode inside a re-included foreign subtree" {
    # The .system re-include matches a whole subtree, and rsync takes the FIRST
    # matching rule — so if it were ordered ahead of the __pycache__ exclude it
    # would drag the exact thing back that aborted the 2026-07-30 deploy.
    ln -s "../../.apm/skills" "$SRC/skills"
    mkdir -p "$BK/skills/.system/imagegen/__pycache__"
    echo "keep" > "$BK/skills/.system/imagegen/SKILL.md"
    echo "junk" > "$BK/skills/.system/imagegen/__pycache__/m.cpython-311.pyc"

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ -f "$TGT/skills/.system/imagegen/SKILL.md" ]                 # foreign install restored
    [ ! -e "$TGT/skills/.system/imagegen/__pycache__" ]            # bytecode still skipped
}

@test "restore_runtime_state restores a user-authored agent but not Manifest's role files" {
    mkdir -p "$SRC/agents" "$BK/agents"
    echo "mine"      > "$BK/agents/my-own-agent.md"   # user's, nothing redeploys it
    echo "stale"     > "$BK/agents/scout.md"          # Manifest's; the gate owns it
    : > "$BK/agents/.pilotfish"                       # marker; the gate is sole writer

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ -f "$TGT/agents/my-own-agent.md" ]              # survives (spec FR-008/SC-003)
    [ ! -e "$TGT/agents/scout.md" ]                   # gate redeploys or prunes it
    [ ! -e "$TGT/agents/.pilotfish" ]                 # never restored stale
}

@test "restore_runtime_state excludes .agent_outputs (recreated as a symlink later)" {
    # .agent_outputs is rebuilt by create_symlink into $MANIFEST_OUTPUT_DIR, so
    # restoring it from the backup is wasted/expensive work that gets wiped.
    mkdir -p "$BK/.agent_outputs/big"
    echo out > "$BK/.agent_outputs/big/run.log"

    run restore_runtime_state "$BK" "$TGT" "$SRC"
    assert_success

    [ ! -e "$TGT/.agent_outputs" ]                   # NOT restored
    [ -f "$TGT/plugins/installed_plugins.json" ]     # other runtime still restored
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

# --- a partial restore must not destroy the home -----------------------------
#
# The live directory has already been `mv`'d into the backup by the time this
# runs. Under `set -e` an unguarded rsync turns one unreadable file into an
# aborted deploy with NO ~/.claude at all. Observed 2026-07-30: a stale
# __pycache__ entry inside a bundled venv changed under rsync mid-copy, rsync
# exited non-zero, bootstrap stopped, and the home was left with runtime state
# only — no scripts/, config/, or references/.

@test "restore_runtime_state survives a failing rsync instead of aborting" {
    local target="$SANDBOX/target"
    mkdir -p "$target"
    # Shadow rsync with a stub that always fails, the way a vanished source file
    # makes the real one exit 23/24.
    mkdir -p "$SANDBOX/stub"
    printf '#!/bin/sh\necho "rsync: some files vanished" >&2\nexit 23\n' > "$SANDBOX/stub/rsync"
    chmod +x "$SANDBOX/stub/rsync"

    run env PATH="$SANDBOX/stub:$PATH" bash -c "
        source '$REPO_ROOT/bootstrap/lib/common.sh'
        source '$REPO_ROOT/bootstrap/lib/deploy.sh'
        set -e
        restore_runtime_state '$BK' '$target' '$SRC'
        echo REACHED_END
    "
    assert_success
    assert_output --partial "REACHED_END"
}

@test "restore_runtime_state names the backup when the restore is incomplete" {
    local target="$SANDBOX/target2"
    mkdir -p "$target" "$SANDBOX/stub2"
    printf '#!/bin/sh\nexit 23\n' > "$SANDBOX/stub2/rsync"
    chmod +x "$SANDBOX/stub2/rsync"

    run env PATH="$SANDBOX/stub2:$PATH" bash -c "
        source '$REPO_ROOT/bootstrap/lib/common.sh'
        source '$REPO_ROOT/bootstrap/lib/deploy.sh'
        set -e
        restore_runtime_state '$BK' '$target' '$SRC'
    "
    assert_success
    assert_output --partial "$BK"
}

@test "restore_runtime_state skips regenerable bytecode caches" {
    local target="$SANDBOX/target3"
    mkdir -p "$target" "$BK/security/venv/lib/__pycache__"
    echo "stale" > "$BK/security/venv/lib/__pycache__/mod.cpython-311.pyc"
    run restore_runtime_state "$BK" "$target" "$SRC"
    assert_success
    [ ! -e "$target/security/venv/lib/__pycache__/mod.cpython-311.pyc" ]
}
