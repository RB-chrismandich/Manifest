#!/usr/bin/env bats
# PreToolUse hook: fill in an omitted sub-agent model (subagent_model_default.py).
#
# The hook has a positive and a negative duty and BOTH are gated here. Filling
# the silence is only half of it: a blunt "always set sonnet" would also pass a
# positive-only suite while silently revoking the Opus permission
# docs/MODEL-POLICY.md grants for adversarial verification, and while writing a
# requested model into `fork` sidecars that never served it — corrupting the
# audit that verifies this hook.

bats_require_minimum_version 1.5.0

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    HOOK="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)/subagent_model_default.py"
    TMP="$BATS_TEST_TMPDIR/proj"
    mkdir -p "$TMP/.claude/agents"
    export CLAUDE_PROJECT_DIR="$TMP"
}

# Feed a payload to the hook; stdout is the hook's decision (empty = no change).
run_hook() {
    run --separate-stderr bash -c "printf '%s' '$1' | python3 '$HOOK'"
}

# The model the hook would inject, or empty when it stays silent.
injected() {
    printf '%s' "$1" | python3 "$HOOK" \
        | python3 -c 'import json,sys
raw = sys.stdin.read().strip()
print(json.loads(raw)["hookSpecificOutput"]["updatedInput"].get("model", "") if raw else "")'
}

@test "--help exits 0 and prints Usage" {
    run python3 "$HOOK" --help
    assert_success
    assert_output --partial "Usage"
}

@test "a dispatch with no model is given the default" {
    result="$(injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"general-purpose"}}')"
    assert_equal "$result" "sonnet"
}

@test "an explicit model is never overridden" {
    result="$(injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"general-purpose","model":"opus"}}')"
    assert_equal "$result" ""
}

@test "a whitespace-only model counts as omitted" {
    result="$(injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"general-purpose","model":"  "}}')"
    assert_equal "$result" "sonnet"
}

@test "fork is left alone (it ignores model; injecting would poison the sidecar)" {
    result="$(injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"fork"}}')"
    assert_equal "$result" ""
}

@test "an agent whose frontmatter pins a model is left alone" {
    printf -- '---\nname: verifier\nmodel: opus\n---\nbody\n' > "$TMP/.claude/agents/verifier.md"
    result="$(injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"verifier"}}')"
    assert_equal "$result" ""
}

@test "an agent whose frontmatter omits a model still gets the default" {
    printf -- '---\nname: plain\ndescription: no model here\n---\nbody\n' > "$TMP/.claude/agents/plain.md"
    result="$(injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"plain"}}')"
    assert_equal "$result" "sonnet"
}

@test "other tools are untouched" {
    result="$(injected '{"tool_name":"Bash","tool_input":{"command":"ls"}}')"
    assert_equal "$result" ""
}

@test "the rest of the dispatch input survives the rewrite" {
    out="$(printf '%s' '{"tool_name":"Agent","tool_input":{"prompt":"keep me","description":"d","subagent_type":"general-purpose"}}' | python3 "$HOOK")"
    run python3 -c "import json,sys; i=json.loads(sys.argv[1])['hookSpecificOutput']['updatedInput']; print(i['prompt'], i['description'], i['model'])" "$out"
    assert_success
    assert_output "keep me d sonnet"
}

@test "the default model is overridable" {
    result="$(SUBAGENT_DEFAULT_MODEL=haiku injected '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"general-purpose"}}')"
    assert_equal "$result" "haiku"
}

@test "malformed input fails open: exit 0, no output, no block" {
    run_hook 'not json at all'
    assert_success
    assert_output ""
}

@test "a payload without tool_input fails open" {
    run_hook '{"tool_name":"Agent"}'
    assert_success
    assert_output ""
}

@test "the emitted decision is a valid PreToolUse hook envelope" {
    out="$(printf '%s' '{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"general-purpose"}}' | python3 "$HOOK")"
    run python3 -c "import json,sys; h=json.loads(sys.argv[1])['hookSpecificOutput']; print(h['hookEventName'])" "$out"
    assert_success
    assert_output "PreToolUse"
}
