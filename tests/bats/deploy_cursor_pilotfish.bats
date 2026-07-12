#!/usr/bin/env bats
# Tests for the Cursor side of the pilotfish role-agents toggle (spec
# 2026-07-11 cursor-feature-parity WS-5). Mirrors deploy_pilotfish.bats
# (which covers gate_pilotfish_agents/check_pilotfish_collision generically)
# by exercising them through deploy_cursor_configs() specifically — same
# --enable-pilotfish toggle, same manifest-owned prune semantics, applied to
# $CURSOR_TARGET_DIR/agents instead of the Claude home.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_cursor_pilotfish.XXXXXX")

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    export SCRIPT_DIR="$SANDBOX/repo"
    CURSOR_AGENTS_SRC="$SCRIPT_DIR/configs/cursor/agents"
    mkdir -p "$SCRIPT_DIR/configs/cursor/rules" "$CURSOR_AGENTS_SRC"
    # Minimal but real hooks.json/mcp.json so deploy_cursor_configs' earlier
    # steps are no-ops rather than errors.
    printf '{"version":1,"hooks":{}}' > "$SCRIPT_DIR/configs/cursor/hooks.json"
    printf '{"mcpServers":{}}' > "$SCRIPT_DIR/configs/cursor/mcp.json"

    for a in "${PILOTFISH_AGENT_FILES[@]}"; do
        name="${a%.md}"
        cat > "$CURSOR_AGENTS_SRC/$a" << EOF
---
name: $name
description: Cursor-native fixture for $name.
model: inherit
readonly: false
---

Fixture body for $name.
EOF
    done

    export TARGET_DIR="$SANDBOX/home/.claude" # unused directly; link_shared_assets no-ops on missing targets
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export ENABLE_CURSOR=true
    export ENABLE_PILOTFISH=false
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# ── Enabled: deploys the six Cursor-native agent files ──────────────────────

@test "ENABLE_PILOTFISH=true: deploy_cursor_configs deploys the six Cursor agent files + marker" {
    export ENABLE_PILOTFISH=true
    run deploy_cursor_configs
    assert_success
    for a in scout.md Explore.md mech-executor.md executor.md verifier.md security-executor.md; do
        [ -f "$CURSOR_TARGET_DIR/agents/$a" ]
    done
    [ -f "$CURSOR_TARGET_DIR/agents/.pilotfish" ]
    run bash -c "ls '$CURSOR_TARGET_DIR'/agents/*.md | wc -l | tr -d ' '"
    assert_output "6"
}

@test "ENABLE_PILOTFISH=true: deployed agent carries Cursor-native frontmatter (model: inherit)" {
    export ENABLE_PILOTFISH=true
    run deploy_cursor_configs
    assert_success
    run grep -qxF "model: inherit" "$CURSOR_TARGET_DIR/agents/scout.md"
    assert_success
}

# ── Default / disabled: no cursor pilotfish artifacts ───────────────────────

@test "ENABLE_PILOTFISH=false (default): deploy_cursor_configs deploys rules/mcp/hooks but no agents dir" {
    run deploy_cursor_configs
    assert_success
    [ -d "$CURSOR_TARGET_DIR/rules" ]
    [ -f "$CURSOR_TARGET_DIR/mcp.json" ]
    [ -f "$CURSOR_TARGET_DIR/hooks.json" ]
    [ ! -d "$CURSOR_TARGET_DIR/agents" ]
}

@test "disabling after enabling prunes exactly the manifest-owned Cursor agent files" {
    export ENABLE_PILOTFISH=true
    deploy_cursor_configs
    [ -f "$CURSOR_TARGET_DIR/agents/scout.md" ]

    export ENABLE_PILOTFISH=false
    run deploy_cursor_configs
    assert_success
    [ ! -d "$CURSOR_TARGET_DIR/agents" ]
}

@test "disabling after enabling preserves a coexisting user-authored Cursor agent" {
    export ENABLE_PILOTFISH=true
    deploy_cursor_configs
    echo "my custom cursor agent" > "$CURSOR_TARGET_DIR/agents/my-agent.md"

    export ENABLE_PILOTFISH=false
    run deploy_cursor_configs
    assert_success
    [ -f "$CURSOR_TARGET_DIR/agents/my-agent.md" ]
    assert_equal "$(cat "$CURSOR_TARGET_DIR/agents/my-agent.md")" "my custom cursor agent"
    [ ! -f "$CURSOR_TARGET_DIR/agents/scout.md" ]
    [ ! -f "$CURSOR_TARGET_DIR/agents/.pilotfish" ]
}

# ── Collision guard ──────────────────────────────────────────────────────────

@test "collision: a foreign non-marker ~/.cursor/agents/scout.md blocks ONLY the agents step" {
    mkdir -p "$CURSOR_TARGET_DIR/agents"
    echo "user's own scout" > "$CURSOR_TARGET_DIR/agents/scout.md" # no .pilotfish marker

    export ENABLE_PILOTFISH=true
    run deploy_cursor_configs
    assert_success # non-fatal: rest of the cursor deploy still completes
    assert_output --partial "pilotfish: skipped Cursor role-agents deploy due to collision"
    # The foreign file is untouched — the real safety property under test.
    assert_equal "$(cat "$CURSOR_TARGET_DIR/agents/scout.md")" "user's own scout"
    # Rules/mcp/hooks still deployed despite the agents-step skip.
    [ -d "$CURSOR_TARGET_DIR/rules" ]
    [ -f "$CURSOR_TARGET_DIR/mcp.json" ]
    [ -f "$CURSOR_TARGET_DIR/hooks.json" ]
}

@test "no collision: a differently-named user agent does not block enabling" {
    mkdir -p "$CURSOR_TARGET_DIR/agents"
    echo "user agent" > "$CURSOR_TARGET_DIR/agents/my-agent.md" # not one of the six, no marker

    export ENABLE_PILOTFISH=true
    run deploy_cursor_configs
    assert_success
    refute_output --partial "skipped Cursor role-agents deploy due to collision"
    [ -f "$CURSOR_TARGET_DIR/agents/scout.md" ]
    [ -f "$CURSOR_TARGET_DIR/agents/my-agent.md" ]
}

# ── ENABLE_CURSOR gate takes priority ────────────────────────────────────────

@test "ENABLE_CURSOR=false: no Cursor pilotfish deploy even with ENABLE_PILOTFISH=true" {
    export ENABLE_CURSOR=false
    export ENABLE_PILOTFISH=true
    run deploy_cursor_configs
    assert_success
    [ ! -d "$CURSOR_TARGET_DIR" ] || [ ! -d "$CURSOR_TARGET_DIR/agents" ]
}

# ── Claude behavior is unaffected (spec: "do not change Claude's pilotfish behavior") ──

@test "gate_pilotfish_agents/check_pilotfish_collision remain usable directly against a Claude-style home (unchanged)" {
    CLAUDE_HOME="$SANDBOX/home/.claude"
    mkdir -p "$CLAUDE_HOME/references"
    cat > "$CLAUDE_HOME/CLAUDE.md" << 'EOF'
# Guide

## Reference Index

- `~/.claude/references/antipatterns.md` — guardrail registry.
EOF
    SRC_AGENTS="$REPO_ROOT/configs/claude/agents"
    ENABLE_PILOTFISH=true run gate_pilotfish_agents "$CLAUDE_HOME" "$SRC_AGENTS"
    assert_success
    [ -f "$CLAUDE_HOME/agents/scout.md" ]
    run grep -qxF "model: haiku" "$CLAUDE_HOME/agents/scout.md"
    assert_success
}
