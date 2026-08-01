#!/usr/bin/env bats
# PreToolUse hook: put the Code Constitution in front of the edit
# (constitution_hook.py).
#
# Two properties carry this hook's design and both are gated here.
#
# It is ADVISORY by construction: malformed input, an unsupported language, an
# unhandled tool, and an unwritable state directory must every one of them exit
# 0 without denying. A hook that can block an edit is a hook that will one day
# block the wrong edit, so the failure paths are tested as first-class
# behaviour, not as an afterthought.
#
# And the doctrine block is paid for ONCE per language per session. That dedup
# is the whole token argument for injecting the whole article set at all; a test suite
# that only proves the articles arrive would pass equally well against a hook
# that re-sends them on every keystroke. So the second call is asserted to be
# silent about the articles while still carrying this file's measurements.
#
# HOME and CONSTITUTION_STATE_DIR are both redirected into the per-test tmpdir:
# the session state IS the fixture, and a run against the real ~/.claude/state
# would pass or fail on whatever a previous session happened to leave there.

bats_require_minimum_version 1.5.0

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

setup() {
    HOOK="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)/constitution_hook.py"

    SANDBOX="$BATS_TEST_TMPDIR/sandbox"
    mkdir -p "$SANDBOX"
    export HOME="$SANDBOX"
    export CONSTITUTION_STATE_DIR="$SANDBOX/state"
    PAYLOAD="$SANDBOX/payload.json"
}

# Feed a raw string to the hook exactly as Claude Code would (stdin, no args).
run_raw() {
    printf '%s' "$1" > "$PAYLOAD"
    run bash -c "python3 '$HOOK' < '$PAYLOAD'"
}

# A PreToolUse payload for <session_id> <tool_name> <file_path>.
run_hook() {
    printf '{"session_id":"%s","tool_name":"%s","tool_input":{"file_path":"%s"}}' "$1" "$2" "$3" > "$PAYLOAD"
    run bash -c "python3 '$HOOK' < '$PAYLOAD'"
}

# The additionalContext the hook emitted, or empty when it stayed silent.
context_of() {
    printf '%s' "$1" | python3 -c 'import json,sys
raw = sys.stdin.read().strip()
print(json.loads(raw)["hookSpecificOutput"]["additionalContext"] if raw else "")'
}

@test "--help exits 0 and prints usage" {
    run python3 "$HOOK" --help
    assert_success
    assert_output --partial "Usage: constitution_hook.py"
}

@test "fails open: malformed JSON exits 0 with no output" {
    run_raw 'not json at all {'
    assert_success
    assert_output ""
}

@test "fails open: empty stdin exits 0 with no output" {
    run_raw ''
    assert_success
    assert_output ""
}

@test "an unsupported language (.md) is silent" {
    run_hook s-md Write "$SANDBOX/notes.md"
    assert_success
    assert_output ""
}

@test "a tool the hook does not handle is silent" {
    printf '{"session_id":"s-bash","tool_name":"Bash","tool_input":{"command":"ls -la"}}' > "$PAYLOAD"
    run bash -c "python3 '$HOOK' < '$PAYLOAD'"
    assert_success
    assert_output ""
}

@test "a payload with no file_path is silent" {
    printf '{"session_id":"s-nopath","tool_name":"Write","tool_input":{}}' > "$PAYLOAD"
    run bash -c "python3 '$HOOK' < '$PAYLOAD'"
    assert_success
    assert_output ""
}

@test "a python Write emits a valid PreToolUse envelope carrying the doctrine" {
    printf 'x = 1\n' > "$SANDBOX/mod.py"
    run_hook s-py Write "$SANDBOX/mod.py"
    assert_success

    run python3 -c "import json,sys; h=json.loads(sys.argv[1])['hookSpecificOutput']; print(h['hookEventName'])" "$output"
    assert_success
    assert_output "PreToolUse"
}

@test "the injected context names the constitution and its first article" {
    printf 'x = 1\n' > "$SANDBOX/mod.py"
    run_hook s-py Write "$SANDBOX/mod.py"
    assert_success

    context="$(context_of "$output")"
    assert [ -n "$context" ]
    run printf '%s' "$context"
    assert_output --partial "Code Constitution"
    assert_output --partial "CON-001"
}

@test "a new file still gets context, and it is the test-first guidance" {
    run_hook s-new Write "$SANDBOX/does_not_exist_yet.py"
    assert_success

    context="$(context_of "$output")"
    assert [ -n "$context" ]
    run printf '%s' "$context"
    assert_output --partial "New file"
    assert_output --partial "test"
}

@test "the doctrine is sent once per language per session, not on every edit" {
    printf 'x = 1\n' > "$SANDBOX/one.py"
    printf 'y = 2\n' > "$SANDBOX/two.py"

    run_hook same-session Write "$SANDBOX/one.py"
    assert_success
    assert_output --partial "CON-001"

    # Second edit, same session and same language: the articles have not
    # changed, so paying for them again is the token waste this dedup exists to
    # prevent. The per-file measurements must still arrive.
    run_hook same-session Write "$SANDBOX/two.py"
    assert_success
    refute_output --partial "CON-001"
    refute_output --partial "Code Constitution v"
    assert_output --partial "two.py"

    # A different session has not been told anything yet.
    run_hook other-session Write "$SANDBOX/one.py"
    assert_success
    assert_output --partial "CON-001"
}

@test "the dedup state is written under CONSTITUTION_STATE_DIR, not the real home" {
    printf 'x = 1\n' > "$SANDBOX/one.py"
    run_hook stateful Write "$SANDBOX/one.py"
    assert_success
    assert [ -f "$CONSTITUTION_STATE_DIR/stateful.json" ]

    run cat "$CONSTITUTION_STATE_DIR/stateful.json"
    assert_success
    assert_output --partial "python"
}

@test "an unwritable state dir fails open loudly: exit 0 and context still emitted" {
    # An existing FILE where the state directory belongs: mkdir cannot succeed,
    # and the contract is that the doctrine repeats rather than disappears.
    printf 'not a directory\n' > "$SANDBOX/state-blocker"
    export CONSTITUTION_STATE_DIR="$SANDBOX/state-blocker"

    printf 'x = 1\n' > "$SANDBOX/mod.py"
    run_hook s-blocked Write "$SANDBOX/mod.py"
    assert_success
    assert_output --partial "CON-001"

    # Un-suppressible, therefore repeated: a second call in the same session
    # still carries the doctrine rather than going silent.
    run_hook s-blocked Write "$SANDBOX/mod.py"
    assert_success
    assert_output --partial "CON-001"
}

@test "a Read of an already-narrated language is silent (reads are not re-narrated)" {
    printf 'x = 1\n' > "$SANDBOX/one.py"
    run_hook read-session Write "$SANDBOX/one.py"
    assert_success
    assert_output --partial "CON-001"

    run_hook read-session Read "$SANDBOX/one.py"
    assert_success
    assert_output ""
}
