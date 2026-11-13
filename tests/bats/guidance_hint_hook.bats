#!/usr/bin/env bats
# T017 — guidance_hint.py fires a one-shot hint at a recognized Workflow Moment
# and stays silent on unrelated actions (spec 362, US2; SC-003 mechanism).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
HINT="$REPO_ROOT/configs/claude/scripts/guidance_hint.py"
UV="$(command -v uv)"
UV_CACHE="${UV_CACHE_DIR:-$HOME/.cache/uv}"

setup() {
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
    export UV_CACHE_DIR="$UV_CACHE"
    unset PYTHONPATH PYTHONHOME
    mkdir -p "$HOME/.local/bin" "$HOME/.claude/scripts" "$HOME/.cursor/scripts"
    ln -sf "$UV" "$HOME/.local/bin/uv"
    ln -sf "$HINT" "$HOME/.claude/scripts/guidance_hint.py"
    ln -sf "$HINT" "$HOME/.cursor/scripts/guidance_hint.py"
    "$REPO_ROOT/configs/claude/scripts/merge_runtime_settings.py" \
        "$REPO_ROOT/configs/claude/settings.runtime.json" "$HOME/.claude/settings.json" \
        --host-version 2.1.263 >/dev/null
    local platform command input
    for platform in claude cursor; do
        if [[ "$platform" == claude ]]; then
            command=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(h["command"] for e in d["hooks"]["PreToolUse"] for h in e["hooks"] if "guidance_hint.py" in h["command"]))' "$HOME/.claude/settings.json")
            input='{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}'
        else
            command=$(python3 -c 'import json; d=json.load(open("configs/cursor/hooks.json")); print(d["hooks"]["beforeShellExecution"][0]["command"])')
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
    run bash -c "echo '$(payload "git commit -m wip")' | '$UV' run --quiet --no-project --with pyyaml --python 3.11 '$HINT'"
    assert_success
    assert_output --partial "/project-verify"
}

@test "gh pr create surfaces a PR-open hint" {
    run bash -c "echo '$(payload "gh pr create --fill")' | '$UV' run --quiet --no-project --with pyyaml --python 3.11 '$HINT'"
    assert_success
    assert_output --partial "/"
}

@test "an unrelated command produces no hint (silent, exit 0)" {
    run bash -c "echo '$(payload "ls -la")' | '$UV' run --quiet --no-project --with pyyaml --python 3.11 '$HINT'"
    assert_success
    assert_output ""
}

@test "explicit --moment emits that moment's hint" {
    run "$UV" run --quiet --no-project --with pyyaml --python 3.11 "$HINT" --moment pre-commit
    assert_success
    assert_output --partial "/project-verify"
}

@test "fails open: malformed payload exits 0 with no output" {
    run bash -c "echo 'not json' | '$UV' run --quiet --no-project --with pyyaml --python 3.11 '$HINT'"
    assert_success
    assert_output ""
}

@test "--help works before any dependency load" {
    run "$UV" run --quiet --no-project --with pyyaml --python 3.11 "$HINT" --help
    assert_success
    assert_output --partial "usage:"
}
