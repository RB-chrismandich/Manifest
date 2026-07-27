#!/usr/bin/env bats
# merge_claude_settings_defaults(): repo-shipped top-level default settings (e.g.
# skillListingBudgetFraction) must reach an already-bootstrapped machine whose
# settings.local.json rsync --ignore-existing keeps in place. User-wins: a value
# the user already set is never overwritten. Scope excludes permissions/hooks/
# mcpServers (their own mergers own those) and env (settings.json env only
# reaches subprocesses, never Claude Code's own runtime — so it is not a place we
# ship defaults).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    TMPDIR_T="$(mktemp -d)"
    SRC="$TMPDIR_T/src.json"   # repo-shipped settings.local.json (source of defaults)
    TGT="$TMPDIR_T/tgt.json"   # user's existing live file rsync kept

    command_exists() { command -v "$1" > /dev/null 2>&1; }
    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    print_warning() { echo "WARN: $*"; }
    export -f command_exists print_info print_success print_warning 2> /dev/null || true

    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh" 2> /dev/null || true

    # Repo-shipped defaults the deploy wants every machine to converge toward.
    cat > "$SRC" <<'EOF'
{
  "permissions": { "allow": ["Bash(ls:*)"] },
  "skillListingBudgetFraction": 0.05
}
EOF
}

teardown() {
    rm -rf "$TMPDIR_T"
}

@test "existing install without the default gains skillListingBudgetFraction" {
    cat > "$TGT" <<'EOF'
{
  "permissions": { "allow": ["Bash(git status:*)"] }
}
EOF
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success
    assert_output --partial "Merged repo session defaults"

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['skillListingBudgetFraction'] == 0.05, d.get('skillListingBudgetFraction')
# user's own permissions must not be touched by the defaults merge
assert d['permissions']['allow'] == ['Bash(git status:*)'], d['permissions']
print('default-added')"
    assert_output --partial "default-added"
}

@test "user-set value wins (never overwritten by repo default)" {
    cat > "$TGT" <<'EOF'
{
  "skillListingBudgetFraction": 0.02
}
EOF
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success
    assert_output --partial "already has repo session defaults"

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['skillListingBudgetFraction'] == 0.02, d['skillListingBudgetFraction']
print('user-wins')"
    assert_output --partial "user-wins"
}

@test "a deliberate falsy user value (0.0) is preserved, not overwritten" {
    # Guards the membership check (`k not in tgt`) against a future refactor to a
    # truthiness check (`not tgt.get(k)`), which would clobber an intentional 0.0.
    cat > "$TGT" <<'EOF'
{
  "skillListingBudgetFraction": 0.0
}
EOF
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success
    assert_output --partial "already has repo session defaults"

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['skillListingBudgetFraction'] == 0.0, d['skillListingBudgetFraction']
print('falsy-preserved')"
    assert_output --partial "falsy-preserved"
}

@test "an arbitrary user-only top-level key survives the rewrite" {
    cat > "$TGT" <<'EOF'
{
  "customUserKey": 42
}
EOF
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['customUserKey'] == 42, d               # user key never dropped
assert d['skillListingBudgetFraction'] == 0.05   # default still added alongside
print('user-key-survives')"
    assert_output --partial "user-key-survives"
}

@test "target already has the default is a clean no-op" {
    cat > "$TGT" <<'EOF'
{
  "skillListingBudgetFraction": 0.05
}
EOF
    local before
    before=$(cat "$TGT")
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success
    assert_output --partial "already has repo session defaults"
    assert_equal "$(cat "$TGT")" "$before"
}

@test "missing target file is a no-op (fresh install lands repo copy directly)" {
    run merge_claude_settings_defaults "$SRC" "$TMPDIR_T/absent.json"
    assert_success
}

@test "missing source is a no-op" {
    cat > "$TGT" <<'EOF'
{ "permissions": { "allow": [] } }
EOF
    local before
    before=$(cat "$TGT")
    run merge_claude_settings_defaults "" "$TGT"
    assert_success
    assert_equal "$(cat "$TGT")" "$before"
}

@test "malformed target fails open (untouched, warning)" {
    echo '{ not json' > "$TGT"
    local before
    before=$(cat "$TGT")
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success
    assert_output --partial "WARN"
    assert_equal "$(cat "$TGT")" "$before"
}

@test "defaults merge never strips or mutates hooks/mcpServers/env on the target" {
    cat > "$TGT" <<'EOF'
{
  "hooks": { "SessionStart": [ { "hooks": [ { "type": "command", "command": "x" } ] } ] },
  "mcpServers": { "mine": { "url": "https://internal.example/mcp" } },
  "env": { "MY_VAR": "keep" }
}
EOF
    run merge_claude_settings_defaults "$SRC" "$TGT"
    assert_success

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['hooks']['SessionStart'][0]['hooks'][0]['command'] == 'x', d['hooks']
assert d['mcpServers']['mine']['url'] == 'https://internal.example/mcp', d['mcpServers']
assert d['env']['MY_VAR'] == 'keep', d['env']            # env left entirely alone
assert d['skillListingBudgetFraction'] == 0.05           # default still added alongside
print('siblings-intact')"
    assert_output --partial "siblings-intact"
}

@test "repo settings.local.json does NOT ship an env block (env is subprocess-only)" {
    # Guard the deliberate design decision: ENABLE_PROMPT_CACHING_1H and peers do
    # not belong in settings.json env (no-op for Claude Code's own runtime).
    run python3 -c "
import json
d = json.load(open('$REPO_ROOT/configs/claude/settings.local.json'))
assert 'env' not in d, 'settings.local.json must not ship an env block: %s' % list(d)
# The budget key moved to settings.runtime.json (destination ~/.claude/settings.json):
# settings.local.json is inert at user scope, so the key was never read there.
r = json.load(open('$REPO_ROOT/configs/claude/settings.runtime.json'))
assert 'env' not in r, 'settings.runtime.json must not ship an env block: %s' % list(r)
assert r.get('skillListingBudgetFraction') == 0.05, r.get('skillListingBudgetFraction')
print('no-env-block')"
    assert_output --partial "no-env-block"
}
