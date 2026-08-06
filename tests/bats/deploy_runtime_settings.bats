#!/usr/bin/env bats
# bootstrap/lib/deploy.sh merge_claude_runtime_settings.
#
# Hooks that must reach Claude Code's own runtime go to ~/.claude/settings.json.
# Measured 2026-07-26 on Claude Code 2.1.220 by controlled A/B (same hook, same
# absolute command, only the file differing): a hook in settings.local.json
# fired zero times; the same hook in settings.json fired on every dispatch. An
# absolute path in settings.local.json also never fired, so tilde expansion is
# not the cause. This merger is the deploy path for that fix — and it is gated
# here because an unexercised deploy function is precisely how the hooks became
# inert in the first place.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_runtime_hooks.XXXXXX")
    # Output helpers the function calls; stubbed so the test asserts behaviour,
    # not bootstrap's console formatting.
    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    print_warning() { echo "WARN: $*"; }
    command_exists() { command -v "$1" > /dev/null 2>&1; }
    # Extract to a REAL file, not `source <(...)`: the function embeds a
    # heredoc, and bash cannot re-read a heredoc body from a non-seekable
    # process-substitution FIFO, so the function silently fails to define.
    sed -n '/^merge_claude_runtime_settings()/,/^}/p' "$REPO_ROOT/bootstrap/lib/deploy.sh" > "$SANDBOX/fn.sh"
    # shellcheck disable=SC1090
    source "$SANDBOX/fn.sh"
    SRC="$REPO_ROOT/configs/claude/settings.runtime.json"
    EXISTING_HOME_FIXTURE="$REPO_ROOT/tests/bats/fixtures/deploy_hooks/existing-claude-settings.json"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Commands registered for one event in the target, comma-joined.
commands_for() {
    python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(','.join(h['command'].split('/')[-1] for e in d['hooks'].get(sys.argv[2],[]) for h in e['hooks']))" "$1" "$2"
}

events_in() {
    python3 -c "import json,sys; print(','.join(sorted(json.load(open(sys.argv[1]))['hooks'])))" "$1"
}

materialize_existing_home() {
    python3 -c "
from pathlib import Path
import sys
source, target, home = map(Path, sys.argv[1:])
target.write_text(source.read_text().replace('__HOME__', str(home)))" \
        "$EXISTING_HOME_FIXTURE" "$1" "$HOME"
}

@test "the repo ships the Agent hook in settings.runtime.json" {
    run commands_for "$SRC" PreToolUse
    assert_success
    assert_output --partial "subagent_model_default.py"
}

@test "every global Claude hook ships here, not in the inert settings.local.json" {
    # settings.local.json is inert at user scope (measured), so a hook left there
    # never runs. This is the regression guard: if someone adds a hook back to
    # settings.local.json it is silently dead, and this test is what says so.
    run python3 -c "import json,sys; print('hooks' in json.load(open(sys.argv[1])))" \
        "$REPO_ROOT/configs/claude/settings.local.json"
    assert_output "False"
}

@test "all four hook events survive the migration" {
    run events_in "$SRC"
    assert_success
    assert_output "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit"
}

@test "the remaining global hooks are present and version-pin is plugin-owned" {
    run commands_for "$SRC" PostToolUse
    assert_output --partial "spec_review.sh --silent"
    assert_output --partial "lint_on_edit_hook.sh"
    refute_output --partial "version_pin_hook.sh"
    run commands_for "$SRC" PreToolUse
    assert_output --partial "guidance_hint.py"
    run commands_for "$SRC" SessionStart
    assert_output --partial "deploy_stamp_check.sh"
}

@test "creates the target when it does not exist" {
    run merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_equal "$(events_in "$SANDBOX/settings.json")" "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit"
}

@test "unions into an existing file without clobbering other keys or hooks" {
    printf '%s' '{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"/existing.sh"}]}]}}' \
        > "$SANDBOX/settings.json"
    run merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    assert_success
    run commands_for "$SANDBOX/settings.json" PreToolUse
    assert_output --partial "existing.sh"
    assert_output --partial "subagent_model_default.py"
    run python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['model'])" "$SANDBOX/settings.json"
    assert_output "opus"
}

@test "existing Claude home drops only retired version-pin hook and permissions" {
    materialize_existing_home "$SANDBOX/settings.json"

    run merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    assert_success
    run merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_output --partial "already has"

    run python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
commands = [h.get('command', '') for entries in d['hooks'].values() for entry in entries for h in entry.get('hooks', [])]
assert not any(c.endswith('/.claude/scripts/version_pin_hook.sh') for c in commands), commands
for expected in ('guidance_hint.py', 'spec_review.sh --silent', 'lint_on_edit_hook.sh', 'deploy_stamp_check.sh', '/opt/user-hooks/keep-me.sh'):
    assert sum(c.endswith(expected) for c in commands) == 1, (expected, commands)
assert d['model'] == 'opus'
allow = d['permissions']['allow']
retired = {
    'Bash(~/.claude/scripts/version_pin.sh:*)',
    'Bash(~/.claude/scripts/version_pin_hook.sh:*)',
}
assert retired.isdisjoint(allow), allow
assert allow[:4] == [
    'Bash(/opt/user-hooks/keep-before.sh:*)',
    'Bash(~/.claude/scripts/guidance_hint.py:*)',
    'Bash(~/.claude/scripts/version_pin.sh --check:*)',
    'Bash(/opt/user-hooks/keep-after.sh:*)',
], allow
print('legacy-removed-unrelated-preserved')" "$SANDBOX/settings.json"
    assert_success
    assert_output "legacy-removed-unrelated-preserved"
}

@test "is idempotent: a second run does not duplicate the entry" {
    merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    run merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_output --partial "already has"
    # Expected count comes from the source, not a literal: the invariant under
    # test is "a second merge adds nothing", and a hardcoded total makes every
    # legitimately-added hook look like a duplication bug.
    run python3 -c "
import json,sys
count = lambda p: sum(len(e['hooks']) for ev in json.load(open(p))['hooks'].values() for e in ev)
merged, source = count(sys.argv[1]), count(sys.argv[2])
print('%d hooks (source ships %d)' % (merged, source))
sys.exit(0 if merged == source else 1)" "$SANDBOX/settings.json" "$SRC"
    assert_success
}

@test "expands ~ so Claude Code receives an absolute command" {
    merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    run python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['hooks']['PreToolUse'][0]['hooks'][0]['command'])" "$SANDBOX/settings.json"
    assert_success
    [[ "$output" == /* ]] || { echo "command not absolute: $output"; false; }
}

@test "the deployed hook command points at a real script" {
    merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    cmd="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['hooks']['PreToolUse'][0]['hooks'][0]['command'])" "$SANDBOX/settings.json")"
    # The deployed copy may be absent on a machine that never bootstrapped, so
    # assert against the repo source, which must always exist.
    [ -f "$REPO_ROOT/configs/claude/scripts/$(basename "$cmd")" ] \
        || { echo "no repo source for $cmd"; false; }
}

@test "a missing source is a skip, not a failure (fail-open)" {
    run merge_claude_runtime_settings "$SANDBOX/absent.json" "$SANDBOX/settings.json"
    assert_success
    [ ! -f "$SANDBOX/settings.json" ] || { echo "created a target from a missing source"; false; }
}

@test "an unparseable target is a warning, not a clobber" {
    printf 'not json' > "$SANDBOX/settings.json"
    run merge_claude_runtime_settings "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_output --partial "WARN"
    assert_equal "$(cat "$SANDBOX/settings.json")" "not json"
}

@test "deploy.sh calls the merger in both the merge and full-copy paths" {
    run grep -c 'merge_claude_runtime_settings "\$source_dir/settings.runtime.json"' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_success
    assert_output "2"
}
