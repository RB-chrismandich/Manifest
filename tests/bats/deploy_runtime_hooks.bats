#!/usr/bin/env bats
# bootstrap/lib/deploy.sh merge_claude_runtime_hooks.
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
    sed -n '/^merge_claude_runtime_hooks()/,/^}/p' "$REPO_ROOT/bootstrap/lib/deploy.sh" > "$SANDBOX/fn.sh"
    # shellcheck disable=SC1090
    source "$SANDBOX/fn.sh"
    SRC="$REPO_ROOT/configs/claude/settings.hooks.json"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

matchers() {
    python3 -c "import json,sys; print(','.join(e.get('matcher','') for e in json.load(open(sys.argv[1]))['hooks']['PreToolUse']))" "$1"
}

@test "the repo ships the Agent hook in settings.hooks.json" {
    run python3 -c "import json,sys; h=json.load(open(sys.argv[1]))['hooks']['PreToolUse']; print(h[0]['matcher'], h[0]['hooks'][0]['command'])" "$SRC"
    assert_success
    assert_output --partial "Agent"
    assert_output --partial "subagent_model_default.py"
}

@test "creates the target when it does not exist" {
    run merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_equal "$(matchers "$SANDBOX/settings.json")" "Agent"
}

@test "unions into an existing file without clobbering other keys or hooks" {
    printf '%s' '{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"/existing.sh"}]}]}}' \
        > "$SANDBOX/settings.json"
    run merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_equal "$(matchers "$SANDBOX/settings.json")" "Bash,Agent"
    run python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['model'])" "$SANDBOX/settings.json"
    assert_output "opus"
}

@test "is idempotent: a second run does not duplicate the entry" {
    merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    run merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_output --partial "already has"
    assert_equal "$(matchers "$SANDBOX/settings.json")" "Agent"
}

@test "expands ~ so Claude Code receives an absolute command" {
    merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    run python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['hooks']['PreToolUse'][0]['hooks'][0]['command'])" "$SANDBOX/settings.json"
    assert_success
    [[ "$output" == /* ]] || { echo "command not absolute: $output"; false; }
}

@test "the deployed hook command points at a real script" {
    merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    cmd="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['hooks']['PreToolUse'][0]['hooks'][0]['command'])" "$SANDBOX/settings.json")"
    # The deployed copy may be absent on a machine that never bootstrapped, so
    # assert against the repo source, which must always exist.
    [ -f "$REPO_ROOT/configs/claude/scripts/$(basename "$cmd")" ] \
        || { echo "no repo source for $cmd"; false; }
}

@test "a missing source is a skip, not a failure (fail-open)" {
    run merge_claude_runtime_hooks "$SANDBOX/absent.json" "$SANDBOX/settings.json"
    assert_success
    [ ! -f "$SANDBOX/settings.json" ] || { echo "created a target from a missing source"; false; }
}

@test "an unparseable target is a warning, not a clobber" {
    printf 'not json' > "$SANDBOX/settings.json"
    run merge_claude_runtime_hooks "$SRC" "$SANDBOX/settings.json"
    assert_success
    assert_output --partial "WARN"
    assert_equal "$(cat "$SANDBOX/settings.json")" "not json"
}

@test "deploy.sh calls the merger in both the merge and full-copy paths" {
    run grep -c 'merge_claude_runtime_hooks "\$source_dir/settings.hooks.json"' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_success
    assert_output "2"
}
