#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUNDLE="$REPO_ROOT/plugins/manifest-security"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/security-runtime.XXXXXX")"
    export HOME="$SANDBOX/home"
    export XDG_STATE_HOME="$SANDBOX/state"
    export XDG_CONFIG_HOME="$SANDBOX/config"
    export XDG_DATA_HOME="$SANDBOX/data"
    mkdir -p "$HOME" "$XDG_STATE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$SANDBOX/repo"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "security CI helper runs below the bundle with empty home" {
    cd "$SANDBOX/repo"
    printf 'stages: [test]\n' > .gitlab-ci.yml

    run "$BUNDLE/runtime/bin/ci_platform.sh"
    assert_success
    assert_output "gitlab-ci"
}

@test "security instructions use local doctrine and qualified skill interfaces" {
    run bash -c "grep -R -nE '(configs/claude|~/.claude/(scripts|references)|manifest parallel-agent|parallel_agent.py|learning_capture.sh|plugins/manifest-ops)' '$BUNDLE/skills' --include='SKILL.md' || true"
    assert_output ""

    # Qualified form since the `[[skill:]]` convention was retired
    # (2026-08-27, Phase 0 item 4 option (b)).
    run grep -R -q 'manifest-workspace:parallel-agent' "$BUNDLE/skills"
    assert_success
    run grep -R -q 'manifest-workspace:learning-capture' "$BUNDLE/skills"
    assert_success
}

@test "security references are packaged in the owning bundle" {
    [ -s "$BUNDLE/runtime/references/ci/gitlab-ci-triggers.md" ]
    [ -s "$BUNDLE/runtime/references/antipatterns.md" ]
    [ -s "$BUNDLE/runtime/references/code-constitution.md" ]
}
