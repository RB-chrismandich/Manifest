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

# ---- end-to-end: deploy_configs() honoring ENABLE_CLAUDE for the "claude"
# entry (#549 follow-up). The unit tests above hand-place files and never
# exercise the real deploy path, so they could not catch that deploy_configs()
# used to redeploy $TARGET_DIR/CLAUDE.md unconditionally — making the "claude"
# entry in warn_stale_disabled_configs' entries array a guaranteed false
# positive on every `--disable-claude` run (a documented workflow, README:284).
# These drive the REAL deploy_configs() against the real repo source.

setup_e2e_deploy() {
    export SCRIPT_DIR="$REPO_ROOT"
    export HOME="$SANDBOX/home"
    export TARGET_DIR="$HOME/.claude"
    export MANIFEST_OUTPUT_DIR="$HOME/.manifest/outputs"
    export FORCE=false

    # Isolate heavy/secondary routines unrelated to this behavior (network,
    # other assistants) — mirrors deploy_runtime_state_e2e.bats.
    write_services_config()      { :; }
    deploy_cursor_configs()      { :; }
    deploy_gemini_configs()      { :; }
    deploy_codex_configs()       { :; }
    deploy_antigravity_configs() { :; }
    sync_skillshare_targets()    { :; }
    deploy_sync_skills()         { :; }
}

@test "e2e fresh install with ENABLE_CLAUDE=false deploys shared infra but not CLAUDE.md" {
    setup_e2e_deploy
    export ENABLE_CLAUDE=false

    deploy_configs

    [ ! -e "$TARGET_DIR/CLAUDE.md" ]
    # Shared infra other assistants symlink into must still be deployed —
    # disabling Claude must not starve an enabled Gemini/Cursor/Codex/Antigravity.
    [ -d "$TARGET_DIR/config" ]
    [ -d "$TARGET_DIR/scripts" ]
    [ -d "$TARGET_DIR/skills/code-audit" ]

    # And the warning function's premise now holds: nothing was ever deployed,
    # so there is nothing stale to warn about.
    export GEMINI_TARGET_DIR="$HOME/.gemini" CURSOR_TARGET_DIR="$HOME/.cursor" \
        CODEX_TARGET_DIR="$HOME/.codex" ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true ENABLE_ANTIGRAVITY=true
    run warn_stale_disabled_configs
    assert_success
    refute_output --partial "claude"
}

@test "e2e re-deploy with ENABLE_CLAUDE=false leaves a prior CLAUDE.md stale, and the warning fires" {
    setup_e2e_deploy
    export ENABLE_CLAUDE=true
    deploy_configs
    [ -f "$TARGET_DIR/CLAUDE.md" ]
    grep -q "Claude Orchestration Guide" "$TARGET_DIR/CLAUDE.md"

    # Simulate the user now running --reconfigure --disable-claude: the repo's
    # CLAUDE.md must NOT be refreshed, and the pre-existing copy must be left
    # exactly as-is (stale), not deleted.
    echo "STALE PRIOR CONTENT" > "$TARGET_DIR/CLAUDE.md"
    export ENABLE_CLAUDE=false FORCE=true
    deploy_configs

    [ -f "$TARGET_DIR/CLAUDE.md" ]
    assert_equal "$(cat "$TARGET_DIR/CLAUDE.md")" "STALE PRIOR CONTENT"
    # Shared infra was still refreshed regardless of the Claude toggle.
    [ -d "$TARGET_DIR/config" ]

    export GEMINI_TARGET_DIR="$HOME/.gemini" CURSOR_TARGET_DIR="$HOME/.cursor" \
        CODEX_TARGET_DIR="$HOME/.codex" ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export ENABLE_GEMINI=true ENABLE_CURSOR=true ENABLE_CODEX=true ENABLE_ANTIGRAVITY=true
    run warn_stale_disabled_configs
    assert_success
    assert_output --partial "claude"
    assert_output --partial "$TARGET_DIR/CLAUDE.md"
}

@test "e2e ENABLE_CLAUDE=true (default) still (re)deploys CLAUDE.md fresh from source" {
    setup_e2e_deploy
    export ENABLE_CLAUDE=true
    mkdir -p "$TARGET_DIR"
    echo "old content" > "$TARGET_DIR/CLAUDE.md"

    export FORCE=true
    deploy_configs

    [ -f "$TARGET_DIR/CLAUDE.md" ]
    grep -q "Claude Orchestration Guide" "$TARGET_DIR/CLAUDE.md"
    [ "$(cat "$TARGET_DIR/CLAUDE.md")" != "old content" ]
}

# ---- verify_installation: CLAUDE.md required_files guard (#549 follow-up) ----
#
# deploy_configs() skips copying CLAUDE.md when ENABLE_CLAUDE is false (see the
# e2e tests above), but verify_installation()'s required_files array used to
# require "$TARGET_DIR/CLAUDE.md" unconditionally — so a `--disable-claude`
# bootstrap followed by `verify` falsely reported "Missing: CLAUDE.md". Fixed
# the same way the pre-existing Antigravity entry in the same array is
# guarded: only require CLAUDE.md when ENABLE_CLAUDE is (default-)true.

setup_verify_installation() {
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME"
    export MANIFEST_STATE_DIR="$HOME/.manifest"
    export MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/orchestration/outputs"
    export MANIFEST_TMP_DIR="$MANIFEST_STATE_DIR/tmp"
    export ENABLE_GH=false ENABLE_GLAB=false
}

@test "verify_installation does not report CLAUDE.md as missing when ENABLE_CLAUDE is false" {
    export ENABLE_CLAUDE=false
    setup_verify_installation
    # No $TARGET_DIR/CLAUDE.md written — mirrors a real --disable-claude deploy.
    run verify_installation
    refute_output --partial "Missing: ${TARGET_DIR#"$HOME"/}/CLAUDE.md"
    refute_output --partial "$TARGET_DIR/CLAUDE.md"
}

@test "verify_installation still reports CLAUDE.md as Found when ENABLE_CLAUDE is true and file present" {
    export ENABLE_CLAUDE=true
    setup_verify_installation
    mkdir -p "$TARGET_DIR"
    echo "guide" > "$TARGET_DIR/CLAUDE.md"
    run verify_installation
    assert_output --partial "Found:"
    assert_output --partial "$TARGET_DIR/CLAUDE.md"
}

@test "verify_installation still reports CLAUDE.md as Missing when ENABLE_CLAUDE is true and file absent" {
    export ENABLE_CLAUDE=true
    setup_verify_installation
    # No $TARGET_DIR/CLAUDE.md written — a genuinely broken enabled install.
    run verify_installation
    assert_output --partial "Missing:"
    assert_output --partial "$TARGET_DIR/CLAUDE.md"
}
