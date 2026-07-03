#!/usr/bin/env bats
# Tests for Antigravity config wiring.
#
# Antigravity (agy) consumes the shared config but is NOT a parallel_agent.py
# orchestrator: it must not carry the scripts/ (parallel_agent.py) or prompts/
# (orchestration guide) links. It links only config, skills, and .plans — agy
# participates as a provider inside parallel_agent, driven purely by config.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

# ---- committed source: configs/antigravity/ ----

@test "configs/antigravity/ exists" {
    [ -d "$REPO_ROOT/configs/antigravity" ]
}

@test "configs/antigravity/ links only config, skills, .plans to ../claude/ (all resolve)" {
    local ag_dir="$REPO_ROOT/configs/antigravity"
    for name in config skills .plans; do
        [ -L "$ag_dir/$name" ] || { echo "Missing symlink: $name"; false; }
        assert_equal "$(readlink "$ag_dir/$name")" "../claude/$name"
        [ -e "$ag_dir/$name" ] || { echo "Dangling symlink: $name"; false; }
    done
}

@test "configs/antigravity/ does NOT carry scripts or prompts (no parallel_agent orchestrator)" {
    local ag_dir="$REPO_ROOT/configs/antigravity"
    [ ! -e "$ag_dir/scripts" ] || { echo "scripts must not be linked into Antigravity"; false; }
    [ ! -e "$ag_dir/prompts" ] || { echo "prompts must not be linked into Antigravity"; false; }
}

# ---- deploy behavior: deploy_antigravity_configs() ----

setup_deploy() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/deploy_ag.XXXXXX")
    export TARGET_DIR="$SANDBOX/dotclaude"          # ~/.claude — source of symlink targets
    export ANTIGRAVITY_TARGET_DIR="$SANDBOX/dotantigravity"
    export ENABLE_ANTIGRAVITY=true
    mkdir -p "$TARGET_DIR"/scripts "$TARGET_DIR"/config "$TARGET_DIR"/prompts \
        "$TARGET_DIR"/.plans "$TARGET_DIR"/skills
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

@test "deploy_antigravity_configs links config/.plans/skills but not scripts/prompts" {
    setup_deploy
    run deploy_antigravity_configs
    assert_success
    for name in config .plans skills; do
        [ -L "$ANTIGRAVITY_TARGET_DIR/$name" ] || { echo "expected symlink: $name"; false; }
    done
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/scripts" ] || { echo "scripts must not be deployed"; false; }
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/prompts" ] || { echo "prompts must not be deployed"; false; }
}

@test "deploy_antigravity_configs prunes scripts/prompts symlinks left by an earlier bootstrap" {
    setup_deploy
    mkdir -p "$ANTIGRAVITY_TARGET_DIR"
    ln -s "$TARGET_DIR/scripts" "$ANTIGRAVITY_TARGET_DIR/scripts"
    ln -s "$TARGET_DIR/prompts" "$ANTIGRAVITY_TARGET_DIR/prompts"
    run deploy_antigravity_configs
    assert_success
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/scripts" ] || { echo "stale scripts symlink not pruned"; false; }
    [ ! -e "$ANTIGRAVITY_TARGET_DIR/prompts" ] || { echo "stale prompts symlink not pruned"; false; }
}

@test "deploy_antigravity_configs preserves a REAL user scripts dir (never destroys user content)" {
    setup_deploy
    mkdir -p "$ANTIGRAVITY_TARGET_DIR/scripts"
    echo "mine" > "$ANTIGRAVITY_TARGET_DIR/scripts/user.txt"
    run deploy_antigravity_configs
    assert_success
    [ -f "$ANTIGRAVITY_TARGET_DIR/scripts/user.txt" ] || { echo "real user scripts dir was destroyed"; false; }
}

# ---- regression guard: other assistants still get scripts + prompts ----

@test "link_shared_assets without exclude still links scripts and prompts (Cursor/Gemini/Codex path)" {
    setup_deploy
    local dest="$SANDBOX/other"
    mkdir -p "$dest"
    run link_shared_assets "$dest" "Other" "true"
    assert_success
    for name in scripts config prompts .plans skills; do
        [ -L "$dest/$name" ] || { echo "expected symlink for other assistant: $name"; false; }
    done
}
