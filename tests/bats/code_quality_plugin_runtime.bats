#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUNDLE="$REPO_ROOT/plugins/manifest-code-quality"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/code-quality-runtime.XXXXXX")"
    export HOME="$SANDBOX/home"
    export XDG_STATE_HOME="$SANDBOX/state"
    export XDG_DATA_HOME="$SANDBOX/data"
    export XDG_CONFIG_HOME="$SANDBOX/config"
    export UV_NO_NETWORK=1
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONNOUSERSITE=1
    export PYTHONPATH=
    mkdir -p "$HOME" "$XDG_STATE_HOME" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "constitution and smoke commands run from the bundle offline" {
    cd "$SANDBOX"

    run python3 -S -B "$BUNDLE/skills/code-audit-constitution/scripts/constitution_check.py" --list
    assert_success
    assert_output --partial "CON-013"

    run python3 -S -B "$BUNDLE/skills/smoke-manage/scripts/smoke.py" --help
    assert_success
    assert_output --partial "append"
    refute_output --partial "manifest_cli"
}

@test "code-quality instructions contain no legacy runtime commands" {
    run bash -c "grep -R -nE '(configs/claude/scripts|~/.claude/scripts|manifest smoke|parallel_agent.py|learning_capture.sh)' '$BUNDLE/skills' --include='SKILL.md' || true"
    assert_output ""
}
