#!/usr/bin/env bats
# T017 — guidance_hint.py fires a one-shot hint at a recognized Workflow Moment
# and stays silent on unrelated actions (spec 362, US2; SC-003 mechanism).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
HINT="$REPO_ROOT/configs/claude/scripts/guidance_hint.py"
LOCKED_HOME="$REPO_ROOT/configs/claude"
RUNTIME_PYTHON="$LOCKED_HOME/.venv/bin/python3"

setup() {
    [[ -x "$RUNTIME_PYTHON" ]] || fail "locked candidate runtime unavailable: $RUNTIME_PYTHON"
    run env UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never uv sync --locked --check --offline --project "$LOCKED_HOME"
    [[ "$status" -eq 0 ]] || fail "candidate runtime does not match its offline lock: $output"
    export PATH="$LOCKED_HOME/.venv/bin:$PATH"
    # Isolated agent home so rate-limit state never leaks between tests/runs.
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/guidance_hint.XXXXXX")
    export HOME="$SANDBOX"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "merged Claude and registered Cursor launchers work without ambient PyYAML" {
    run env -u PYTHONPATH -u PYTHONHOME python3 -I -S -c 'import yaml'
    assert_failure
    unset PYTHONPATH PYTHONHOME
    mkdir -p "$HOME/.claude/scripts" "$HOME/.cursor/scripts"
    ln -s "$LOCKED_HOME/.venv" "$HOME/.claude/.venv"
    ln -sf "$HINT" "$HOME/.claude/scripts/guidance_hint.py"
    ln -sf "$HINT" "$HOME/.cursor/scripts/guidance_hint.py"
    "$RUNTIME_PYTHON" "$REPO_ROOT/configs/claude/scripts/merge_runtime_settings.py" \
        "$REPO_ROOT/configs/claude/settings.runtime.json" "$HOME/.claude/settings.json" \
        --host-version 2.1.263 >/dev/null
    local platform command input
    for platform in claude cursor; do
        if [[ "$platform" == claude ]]; then
            command=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(h["command"] for e in d["hooks"]["PreToolUse"] for h in e["hooks"] if "guidance_hint.py" in h["command"]))' "$HOME/.claude/settings.json")
            input='{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}'
        else
            command=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["hooks"]["beforeShellExecution"][0]["command"])' "$REPO_ROOT/configs/cursor/hooks.json")
            input='{"command":"git commit -m x","cwd":"/tmp","sandbox":{}}'
        fi
        run bash -c "printf '%s' '$input' | $command"
        assert_success
        assert_output --partial "/project-verify"
        if [[ "$platform" == claude ]]; then
            input='{"tool_name":"Bash","tool_input":{"command":"ls -la"}}'
        else
            input='{"command":"ls -la","cwd":"/tmp","sandbox":{}}'
        fi
        run bash -c "printf '%s' '$input' | $command"
        assert_success
        assert_output ""
    done
}

# Simulate a Claude Code PreToolUse Bash payload on stdin.
payload() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1"; }

@test "git commit surfaces a commit-guidance hint" {
    run bash -c "echo '$(payload "git commit -m wip")' | '$RUNTIME_PYTHON' -I '$HINT'"
    assert_success
    assert_output --partial "/project-verify"
}

@test "gh pr create surfaces a PR-open hint" {
    run bash -c "echo '$(payload "gh pr create --fill")' | '$RUNTIME_PYTHON' -I '$HINT'"
    assert_success
    assert_output --partial "/"
}

@test "an unrelated command produces no hint (silent, exit 0)" {
    run bash -c "echo '$(payload "ls -la")' | '$RUNTIME_PYTHON' -I '$HINT'"
    assert_success
    assert_output ""
}

@test "explicit --moment emits that moment's hint" {
    run "$RUNTIME_PYTHON" -I "$HINT" --moment pre-commit
    assert_success
    assert_output --partial "/project-verify"
}

@test "fails open: malformed payload exits 0 with no output" {
    run bash -c "echo 'not json' | '$RUNTIME_PYTHON' -I '$HINT'"
    assert_success
    assert_output ""
}

@test "--help works before any dependency load" {
    run "$RUNTIME_PYTHON" -I "$HINT" --help
    assert_success
    assert_output --partial "usage:"
}
