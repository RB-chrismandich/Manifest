#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUNDLE="$REPO_ROOT/plugins/manifest-docs"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/docs-runtime.XXXXXX")"
    export HOME="$SANDBOX/home"
    export UV_NO_NETWORK=1
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONNOUSERSITE=1
    export PYTHONPATH=
    mkdir -p "$HOME"
    printf '# Example\n' > "$SANDBOX/README.md"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "docs linter runs from the bundle offline" {
    cd "$SANDBOX"
    run python3 -S -B "$BUNDLE/runtime/docs_lint.py" README.md
    assert_success
    assert_output --partial "0 over cap"
}

@test "docs instructions resolve the adjacent runtime" {
    run bash -c "grep -L '../../runtime/docs_lint.py' '$BUNDLE'/skills/*/SKILL.md || true"
    assert_output ""

    run bash -c "grep -R -nE '(configs/claude|manifest parallel-agent|parallel_agent.py)' '$BUNDLE/skills' --include='SKILL.md' || true"
    assert_output ""
}
