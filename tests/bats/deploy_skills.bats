#!/usr/bin/env bats
# Tests for bootstrap/lib/common.sh deploy_home_skills + deploy.sh skills wiring

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_skills.XXXXXX")
    # Source the helpers under test
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "deploy_home_skills copies real directories from physical source" {
    mkdir -p "$SANDBOX/src/demo-skill"
    echo "body" > "$SANDBOX/src/demo-skill/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/demo-skill" ]
    [ ! -L "$SANDBOX/dest" ]
    assert_equal "$(cat "$SANDBOX/dest/demo-skill/SKILL.md")" "body"
}

@test "deploy_home_skills prunes skills removed from source" {
    mkdir -p "$SANDBOX/src/keep" "$SANDBOX/dest/stale"
    echo k > "$SANDBOX/src/keep/SKILL.md"
    echo s > "$SANDBOX/dest/stale/SKILL.md"

    run deploy_home_skills "$SANDBOX/src" "$SANDBOX/dest"
    assert_success

    [ -d "$SANDBOX/dest/keep" ]
    [ ! -e "$SANDBOX/dest/stale" ]
}

@test "deploy_home_skills fails clearly when source missing" {
    run deploy_home_skills "$SANDBOX/nonexistent" "$SANDBOX/dest"
    assert_failure
    assert_output --partial "not found"
}

@test "deploy_configs (fresh) puts real skill dirs in TARGET and no '~' junk" {
    # Arrange an isolated TARGET and stub the heavy secondary deploys.
    export SCRIPT_DIR="$REPO_ROOT"
    export TARGET_DIR="$SANDBOX/home/.claude"
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export GEMINI_TARGET_DIR="$SANDBOX/home/.gemini"
    export CODEX_TARGET_DIR="$SANDBOX/home/.codex"
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
    export MANIFEST_OUTPUT_DIR="$SANDBOX/home/.manifest/outputs"
    export FORCE=true

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    # Isolate: stub secondary routines that need network/CLIs/other configs.
    write_services_config() { :; }
    deploy_cursor_configs() { :; }
    deploy_gemini_configs() { :; }
    deploy_codex_configs() { :; }
    deploy_antigravity_configs() { :; }
    sync_skillshare_targets() { :; }

    run deploy_configs
    assert_success

    # Real skill dirs landed (sampled), and skills is NOT a symlink.
    [ -d "$TARGET_DIR/skills/code-quality" ]
    [ ! -L "$TARGET_DIR/skills" ]
    # The compat symlink was never copied verbatim into the home dir.
    [ ! -e "$TARGET_DIR/skills/skills" ]
    # No literal tilde dir created anywhere under the sandbox.
    run find "$SANDBOX" -name '~' -maxdepth 6
    assert_output ""
}
