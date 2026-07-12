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

# ---- verify_installation: CLI-tools readiness loop counts antigravity (G15) ----

setup_verify() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/deploy_ag_verify.XXXXXX")
    export HOME="$SANDBOX/home"
    export TARGET_DIR="$HOME/.claude"
    export CURSOR_TARGET_DIR="$HOME/.cursor"
    export GEMINI_TARGET_DIR="$HOME/.gemini"
    export CODEX_TARGET_DIR="$HOME/.codex"
    export ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export MANIFEST_STATE_DIR="$HOME/.manifest"
    export MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/orchestration/outputs"
    export MANIFEST_TMP_DIR="$MANIFEST_STATE_DIR/tmp"
    export ENABLE_CLAUDE=true ENABLE_GEMINI=false ENABLE_CURSOR=false ENABLE_CODEX=false
    export ENABLE_ANTIGRAVITY=true ENABLE_GH=false ENABLE_GLAB=false
    export RED='' GREEN='' BLUE='' YELLOW='' CYAN='' BOLD='' NC=''
    mkdir -p "$HOME"
    MOCK_BIN="$SANDBOX/mock_bin"
    mkdir -p "$MOCK_BIN"
    # Restricted PATH (mocks + system coreutils only) so a real claude/agy/jq
    # already installed on the dev machine can't leak into command_exists checks.
    export PATH="$MOCK_BIN:/usr/bin:/bin"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

make_verify_stub() {
    cat > "$MOCK_BIN/$1" << 'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$MOCK_BIN/$1"
}

@test "verify_installation counts antigravity toward enabled/available so claude+agy-only doesn't falsely warn" {
    setup_verify
    make_verify_stub claude
    make_verify_stub agy
    run verify_installation
    assert_output --partial "agy is available (enabled)"
    refute_output --partial "Only 1 services enabled"
}

@test "verify_installation warns when antigravity is enabled but agy is not installed" {
    setup_verify
    make_verify_stub claude
    run verify_installation
    assert_output --partial "agy is not available (enabled but not installed)"
}

@test "verify_installation reports antigravity as disabled when ENABLE_ANTIGRAVITY is false" {
    setup_verify
    export ENABLE_ANTIGRAVITY=false
    make_verify_stub claude
    run verify_installation
    assert_output --partial "antigravity is disabled"
    refute_output --partial "agy is available"
}

@test "verify_installation required_files checks the antigravity SKILL.md only when enabled" {
    setup_verify
    export ENABLE_ANTIGRAVITY=false
    make_verify_stub claude
    run verify_installation
    refute_output --partial ".antigravity/skills/code-audit/SKILL.md"
}

@test "verify_installation reports the antigravity SKILL.md as Found when deployed and enabled" {
    setup_verify
    make_verify_stub claude
    make_verify_stub agy
    mkdir -p "$ANTIGRAVITY_TARGET_DIR/skills/code-audit"
    echo "skill" > "$ANTIGRAVITY_TARGET_DIR/skills/code-audit/SKILL.md"
    run verify_installation
    assert_output --partial "Found:"
    assert_output --partial ".antigravity/skills/code-audit/SKILL.md"
}

@test "verify_installation reports the antigravity SKILL.md as Missing when enabled but not deployed" {
    setup_verify
    make_verify_stub claude
    make_verify_stub agy
    run verify_installation
    assert_output --partial "Missing:"
    assert_output --partial ".antigravity/skills/code-audit/SKILL.md"
}

# ---- print_summary: antigravity auth hint (G17) ----

@test "print_summary includes an antigravity auth hint when enabled" {
    setup_verify
    export PLATFORM=macos INSTALL_MCP=false SHELL=/bin/bash
    run print_summary
    assert_output --partial "Antigravity:"
    assert_output --partial "agy"
}

@test "print_summary omits the antigravity auth hint when disabled" {
    setup_verify
    export ENABLE_ANTIGRAVITY=false
    export PLATFORM=macos INSTALL_MCP=false SHELL=/bin/bash
    run print_summary
    refute_output --partial "Antigravity:"
}
