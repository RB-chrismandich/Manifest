#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUNDLE="$REPO_ROOT/plugins/manifest-workspace"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/workspace-runtime.XXXXXX")"
    export HOME="$SANDBOX/home"
    export XDG_STATE_HOME="$SANDBOX/state"
    export XDG_DATA_HOME="$SANDBOX/data"
    export XDG_CONFIG_HOME="$SANDBOX/config"
    export UV_NO_NETWORK=1
    export PYTHONDONTWRITEBYTECODE=1
    mkdir -p "$HOME" "$XDG_STATE_HOME" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$SANDBOX/bin"
    ln -s "$(command -v python3)" "$SANDBOX/bin/python3"
    export PATH="$SANDBOX/bin:/usr/bin:/bin"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "workspace commands run from the bundle with empty home and offline XDG state" {
    cd "$SANDBOX"

    run python3 -B "$BUNDLE/skills/parallel-agent/scripts/parallel_agent.py" --help
    assert_success
    refute_output --partial "configs/claude"
    refute_output --partial ".claude"

    run python3 -B "$BUNDLE/skills/help/scripts/command_catalog.py" --all
    assert_success
    assert_output --partial "parallel-agent"

    run python3 -B "$BUNDLE/skills/env-check/scripts/env_check.py" --json
    assert_success
    assert_output --partial '"status"'
}

@test "workspace runtime contains no path arithmetic into repository config" {
    run bash -c "grep -R -nE '(configs/claude|manifest_agent)' \
        '$BUNDLE/skills/parallel-agent/scripts' \
        '$BUNDLE/skills/learning-capture/scripts' \
        '$BUNDLE/skills/help/scripts' \
        '$BUNDLE/skills/env-check/scripts' \
        '$BUNDLE/skills/deploy-reconcile/scripts' \
        '$BUNDLE/skills/skill-evolve/scripts' \
        '$BUNDLE/skills/ai-hooks-integration/scripts' \
        '$BUNDLE/skills/pr-smoke/scripts' --include='*.py' --include='*.sh' || true"
    assert_output ""
}

@test "learning compatibility and pr-smoke execute without network or shared homes" {
    cd "$SANDBOX"

    run python3 -B "$BUNDLE/skills/learning-capture/scripts/learning_capture.py" add \
        --category tool_discovery --language python --title "Offline tool" \
        --description "Uses only bundle-local stdlib." --confidence high
    assert_success
    assert_output --partial '"id": "KB-001"'

    mkdir -p repo
    git -C repo init -q
    run bash -c "cd '$SANDBOX/repo' && '$BUNDLE/skills/pr-smoke/scripts/run_pr_regression.sh' --quick"
    assert_success
    assert_output --partial 'Verdict: PASS'
}
