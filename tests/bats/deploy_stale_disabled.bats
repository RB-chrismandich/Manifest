#!/usr/bin/env bats
# Tests for warn_stale_disabled_configs() — #549.
#
# When a service is disabled, bootstrap skips deploying its configs, but any
# previously deployed copy is left in place and silently goes stale. The deploy
# summary must print a one-line warning naming the service and the stale path.
# Detection is presence-based; the function never deletes or modifies files.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/deploy_stale.XXXXXX")
    export TARGET_DIR="$SANDBOX/dotclaude"
    export GEMINI_TARGET_DIR="$SANDBOX/dotgemini"
    export CURSOR_TARGET_DIR="$SANDBOX/dotcursor"
    export CODEX_TARGET_DIR="$SANDBOX/dotcodex"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/dotantigravity"
    # Default everything enabled; individual tests flip what they exercise.
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true \
        ENABLE_CODEX=true ENABLE_ANTIGRAVITY=true
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "disabled service with a deployed config warns, naming service and path" {
    export ENABLE_CODEX=false
    mkdir -p "$CODEX_TARGET_DIR"
    echo "stale guide" > "$CODEX_TARGET_DIR/AGENTS.md"

    run warn_stale_disabled_configs
    assert_success
    assert_output --partial "codex"
    assert_output --partial "$CODEX_TARGET_DIR/AGENTS.md"
}

@test "disabled service with no deployed config is silent" {
    export ENABLE_CODEX=false
    # No ~/.codex/AGENTS.md written.
    run warn_stale_disabled_configs
    assert_success
    refute_output --partial "codex"
}

@test "enabled service with a deployed config is silent" {
    export ENABLE_CODEX=true
    mkdir -p "$CODEX_TARGET_DIR"
    echo "current guide" > "$CODEX_TARGET_DIR/AGENTS.md"

    run warn_stale_disabled_configs
    assert_success
    refute_output --partial "codex"
}

@test "warns once per disabled-and-present service across multiple services" {
    export ENABLE_GEMINI=false ENABLE_CODEX=false
    mkdir -p "$GEMINI_TARGET_DIR" "$CODEX_TARGET_DIR"
    echo x > "$GEMINI_TARGET_DIR/GEMINI.md"
    echo x > "$CODEX_TARGET_DIR/AGENTS.md"

    run warn_stale_disabled_configs
    assert_success
    assert_output --partial "gemini"
    assert_output --partial "codex"
    # Exactly two warning lines (one per stale service), nothing else.
    assert_equal "$(printf '%s\n' "$output" | grep -c .)" 2
}

@test "detects a deployed cursor rules directory (not just single files)" {
    export ENABLE_CURSOR=false
    mkdir -p "$CURSOR_TARGET_DIR/rules"

    run warn_stale_disabled_configs
    assert_success
    assert_output --partial "cursor"
    assert_output --partial "$CURSOR_TARGET_DIR/rules"
}

@test "detects a dangling deployed symlink left by a prior deploy" {
    export ENABLE_ANTIGRAVITY=false
    mkdir -p "$ANTIGRAVITY_TARGET_DIR"
    ln -s "$SANDBOX/nonexistent-source" "$ANTIGRAVITY_TARGET_DIR/config"

    run warn_stale_disabled_configs
    assert_success
    assert_output --partial "antigravity"
}

@test "warning-only: does not delete or modify the deployed config" {
    export ENABLE_CODEX=false
    mkdir -p "$CODEX_TARGET_DIR"
    echo "keep me" > "$CODEX_TARGET_DIR/AGENTS.md"

    run warn_stale_disabled_configs
    assert_success
    [ -f "$CODEX_TARGET_DIR/AGENTS.md" ]
    assert_equal "$(cat "$CODEX_TARGET_DIR/AGENTS.md")" "keep me"
}

@test "all services enabled and present produces no output" {
    mkdir -p "$TARGET_DIR" "$GEMINI_TARGET_DIR" "$CODEX_TARGET_DIR"
    echo x > "$TARGET_DIR/CLAUDE.md"
    echo x > "$GEMINI_TARGET_DIR/GEMINI.md"
    echo x > "$CODEX_TARGET_DIR/AGENTS.md"

    run warn_stale_disabled_configs
    assert_success
    assert_output ""
}
