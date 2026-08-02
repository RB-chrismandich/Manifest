#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUNDLE="$REPO_ROOT/plugins/manifest-ops"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/ops-runtime.XXXXXX")"
    export HOME="$SANDBOX/home"
    export XDG_STATE_HOME="$SANDBOX/state"
    export XDG_CONFIG_HOME="$SANDBOX/config"
    export XDG_DATA_HOME="$SANDBOX/data"
    mkdir -p "$HOME" "$XDG_STATE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$SANDBOX/repo"

    printf '#!/bin/sh\nprintf "2.31.0\\tabc123\\n"\n' > "$SANDBOX/resolver"
    chmod +x "$SANDBOX/resolver"
    export VERSION_PIN_RESOLVER="$SANDBOX/resolver"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "ops CI and version-pin commands run below the bundle with empty home" {
    cd "$SANDBOX/repo"
    mkdir -p .github/workflows
    printf 'name: ci\n' > .github/workflows/ci.yml

    run "$BUNDLE/runtime/bin/ci_platform.sh"
    assert_success
    assert_output "github-actions"

    printf 'requests\n' > requirements.txt
    run "$BUNDLE/runtime/bin/version_pin.sh" requirements.txt
    assert_success
    assert_equal "$(cat requirements.txt)" "requests==2.31.0 --hash=sha256:abc123"
}

@test "ops advisory hook is scoped and never rewrites a saved file" {
    cd "$SANDBOX/repo"
    printf 'requests\n' > requirements.txt

    run bash -c "printf '%s' '{\"tool_input\":{\"file_path\":\"$SANDBOX/repo/requirements.txt\"}}' | '$BUNDLE/runtime/bin/version_pin_hook.sh'"
    assert_success
    assert_equal "$(cat requirements.txt)" "requests"

    printf 'prose\n' > README.md
    run bash -c "printf '%s' '{\"tool_input\":{\"file_path\":\"$SANDBOX/repo/README.md\"}}' | '$BUNDLE/runtime/bin/version_pin_hook.sh'"
    assert_success
    assert_output ""
}

@test "ops instructions contain no shared runtime commands" {
    run bash -c "grep -R -nE '(configs/claude|~/.claude/(scripts|references)|version_pin_hook.sh)' '$BUNDLE/skills' --include='SKILL.md' || true"
    assert_output ""
}
