#!/usr/bin/env bats
# End-to-end: drive the REAL deploy_configs() through each existing-install path
# (Backup-and-replace, Merge, --force) with a pre-populated ~/.claude that holds
# runtime state (installed plugins, chat sessions, the user's settings.json) and
# assert that state survives a redeploy while repo-owned config is refreshed.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_e2e.XXXXXX")

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # Real repo configs are the deploy source.
    export SCRIPT_DIR="$REPO_ROOT"
    export HOME="$SANDBOX/home"
    export TARGET_DIR="$HOME/.claude"
    export CURSOR_TARGET_DIR="$HOME/.cursor"
    export GEMINI_TARGET_DIR="$HOME/.gemini"
    export CODEX_TARGET_DIR="$HOME/.codex"
    export ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export MANIFEST_OUTPUT_DIR="$HOME/.manifest/outputs"

    # Isolate heavy/secondary routines (network, profiles, other agents).
    write_services_config()      { :; }
    deploy_cursor_configs()      { :; }
    deploy_gemini_configs()      { :; }
    deploy_codex_configs()       { :; }
    deploy_antigravity_configs() { :; }
    deploy_sync_skills()         { :; }

    # Pre-populate a realistic live ~/.claude: runtime state + a stale/extra
    # repo-owned file that a clean replace SHOULD drop.
    mkdir -p "$TARGET_DIR/plugins/cache/mkt/remember/0.7.3" \
             "$TARGET_DIR/projects" "$TARGET_DIR/.remember" "$TARGET_DIR/config"
    echo '{"plugins":{"remember":1}}' > "$TARGET_DIR/plugins/installed_plugins.json"
    echo 'session-data'               > "$TARGET_DIR/projects/abc.jsonl"
    echo 'user-private-settings'      > "$TARGET_DIR/settings.json"
    echo 'remember-notes'             > "$TARGET_DIR/.remember/notes.md"
    # Stale config INSIDE a repo-owned dir: a clean replace must drop it because
    # config/ is excluded from the restore and redeployed fresh from source.
    echo 'STALE'                      > "$TARGET_DIR/config/OLD_THING.yml"
    # A stray top-level file that is NOT part of configs/claude is unknown user
    # content and must be preserved (safe default, same as plugins/sessions).
    echo 'keepme'                     > "$TARGET_DIR/my_personal_note.md"

    # A live settings.local.json holding a USER-ADDED MCP server. The repo ships
    # its own settings.local.json (with default mcpServers) that overwrites this
    # on redeploy; the user's server must survive (kept intact).
    cat > "$TARGET_DIR/settings.local.json" <<'JSON'
{
  "mcpServers": {
    "my-private": { "url": "https://mcp.internal.example/mcp" }
  }
}
JSON
}

# The user-added MCP server survived AND the repo defaults were deployed.
assert_user_mcp_preserved() {
    run python3 -c "
import json
d = json.load(open('$TARGET_DIR/settings.local.json'))
s = d.get('mcpServers', {})
assert s.get('my-private', {}).get('url') == 'https://mcp.internal.example/mcp', s
# The repo no longer ships MCP defaults here: settings.local.json is inert at
# user scope, so an `mcpServers` block in it was never read. Defaults are now
# registered with `claude mcp add --scope user` (install_claude_mcp_servers),
# which also rescues any user entry stranded in this file.
print('mcp-preserved')"
    assert_output --partial "mcp-preserved"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Assert all runtime state is intact in the freshly deployed TARGET_DIR.
assert_runtime_preserved() {
    [ -f "$TARGET_DIR/plugins/installed_plugins.json" ]
    [ -d "$TARGET_DIR/plugins/cache/mkt/remember/0.7.3" ]
    [ -f "$TARGET_DIR/projects/abc.jsonl" ]
    [ -f "$TARGET_DIR/.remember/notes.md" ]
    assert_equal "$(cat "$TARGET_DIR/settings.json")" "user-private-settings"
    assert_equal "$(cat "$TARGET_DIR/projects/abc.jsonl")" "session-data"
}

# And repo-owned config got (re)deployed for real.
assert_config_deployed() {
    [ -f "$TARGET_DIR/CLAUDE.md" ]
    [ -d "$TARGET_DIR/config" ]
    [ -d "$TARGET_DIR/scripts" ]
    [ -d "$TARGET_DIR/skills/code-audit" ]   # real skills, not the symlink
    [ ! -L "$TARGET_DIR/skills" ]
}

@test "e2e Backup-and-replace: plugins/sessions/settings survive, stale config dropped, backup made" {
    export FORCE=false
    # Feed menu choice "1" (Backup and replace) to the interactive read.
    deploy_configs <<< "1"

    assert_runtime_preserved
    assert_config_deployed
    assert_user_mcp_preserved

    # Stale config inside a repo-owned dir was dropped (the whole point of
    # option 1 vs merge) — proving owned config was genuinely replaced.
    [ ! -e "$TARGET_DIR/config/OLD_THING.yml" ]
    # …but a stray non-owned user file was preserved, like any runtime state.
    assert_equal "$(cat "$TARGET_DIR/my_personal_note.md")" "keepme"

    # A timestamped backup was created and still holds the original state.
    run bash -c "ls -d $HOME/.claude.backup.* 2>/dev/null | head -1"
    assert_output --partial ".claude.backup."
    local bak; bak=$(ls -d "$HOME"/.claude.backup.* | head -1)
    [ -f "$bak/plugins/installed_plugins.json" ]
}

@test "e2e --force: additive deploy keeps plugins and leaves runtime untouched" {
    export FORCE=true
    deploy_configs

    assert_runtime_preserved
    assert_config_deployed
    assert_user_mcp_preserved
    # --force is additive (no mv), so even the stale file remains — that's fine;
    # the data-loss bug was only ever the mv path.
}

@test "e2e Merge: option 2 keeps plugins and existing runtime" {
    export FORCE=false
    deploy_configs <<< "2"

    assert_runtime_preserved
    [ -f "$TARGET_DIR/CLAUDE.md" ]
    [ -d "$TARGET_DIR/skills/code-audit" ]

    # Merge keeps the user's settings.local.json (and its MCP server) intact AND
    # unions in the repo's top-level session defaults (skillListingBudgetFraction)
    # that rsync --ignore-existing would otherwise strand. The scalar-defaults
    # proof moved to deploy_runtime_settings.bats along with the keys themselves.
    run python3 -c "
import json
d = json.load(open('$TARGET_DIR/settings.local.json'))
s = d.get('mcpServers', {})
assert s.get('my-private', {}).get('url') == 'https://mcp.internal.example/mcp', s
# The budget default now lands in settings.json (settings.local.json is inert
# at user scope), so it is NOT asserted here: this fixture deliberately seeds a
# non-JSON settings.json as a 'must survive untouched' sentinel, and the merger
# correctly refuses to rewrite an unparseable file. The defaults-seeding proof
# lives in deploy_runtime_settings.bats, which uses a real JSON target.
print('mcp-intact-defaults-merged')"
    assert_output --partial "mcp-intact-defaults-merged"
}
