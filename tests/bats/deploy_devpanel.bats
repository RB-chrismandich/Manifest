#!/usr/bin/env bats
# Tests for the devpanel critic-gated role-agents toggle.
# Covers the common.sh gate/collision/pointer helpers plus source-file invariants.
# Mirrors deploy_pilotfish.bats structure — devpanel is a separate, independently
# gated agent set (developer/debugger/tester + spec-guard/chaos-engineer) that
# deploys into the SAME ~/.claude/agents dir as pilotfish, on disjoint filenames.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SRC_AGENTS="$REPO_ROOT/configs/claude/agents-devpanel"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_devpanel.XXXXXX")
    HOME_DIR="$SANDBOX/.claude"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Simulate the post-rsync state. agents-devpanel/ is a Manifest-internal source dir
# (not rsync'd itself); references/devpanel-delegation.md IS excluded from the
# wholesale rsync (the gate deploys it from source when enabled), so the seed sets
# up only what rsync actually lands: CLAUDE.md + settings.json.
seed_deployed_home() {
    mkdir -p "$HOME_DIR/references"
    cat > "$HOME_DIR/CLAUDE.md" <<'EOF'
# Guide

## Reference Index

- `~/.claude/references/antipatterns.md` — guardrail registry.
EOF
    printf '{"model":"claude-opus-4-8"}\n' > "$HOME_DIR/settings.json"
}

# ---- gate: enabled ---------------------------------------------------------

@test "gate enabled: stamps marker and injects exactly one pointer line" {
    seed_deployed_home
    ENABLE_DEVPANEL=true run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/.devpanel" ]
    [ -d "$HOME_DIR/agents" ]
    run grep -cF 'devpanel-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "1"
}

@test "gate enabled: deploys exactly the five role files + the reference from source" {
    seed_deployed_home
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    for a in developer.md debugger.md tester.md spec-guard.md chaos-engineer.md; do
        [ -f "$HOME_DIR/agents/$a" ]
    done
    run bash -c "ls '$HOME_DIR'/agents/*.md | wc -l | tr -d ' '"
    assert_output "5"
    [ -f "$HOME_DIR/references/devpanel-delegation.md" ]
}

@test "gate enabled: pointer injection is idempotent (no duplicate on re-run)" {
    seed_deployed_home
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    run grep -cF 'devpanel-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "1"
}

@test "gate enabled: does not touch settings.json" {
    seed_deployed_home
    before="$(cat "$HOME_DIR/settings.json")"
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_equal "$(cat "$HOME_DIR/settings.json")" "$before"
}

@test "gate enabled: coexists with pilotfish in the same agents dir, no collision" {
    seed_deployed_home
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$REPO_ROOT/configs/claude/agents"
    ENABLE_DEVPANEL=true run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/scout.md" ]        # pilotfish role
    [ -f "$HOME_DIR/agents/developer.md" ]    # devpanel role
    [ -f "$HOME_DIR/agents/.pilotfish" ]
    [ -f "$HOME_DIR/agents/.devpanel" ]
    run grep -cF 'pilotfish-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "1"
    run grep -cF 'devpanel-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "1"
}

# ---- gate: disabled (clean reverse) ----------------------------------------

@test "gate disabled: removes exactly the devpanel artifacts, nothing else" {
    seed_deployed_home
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    mkdir -p "$HOME_DIR/skills/other"
    echo keep > "$HOME_DIR/skills/other/x"
    before_settings="$(cat "$HOME_DIR/settings.json")"

    ENABLE_DEVPANEL=false run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success

    [ ! -d "$HOME_DIR/agents" ]
    [ ! -f "$HOME_DIR/references/devpanel-delegation.md" ]
    run grep -cF 'devpanel-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "0"
    [ -f "$HOME_DIR/skills/other/x" ]
    assert_equal "$(cat "$HOME_DIR/settings.json")" "$before_settings"
}

@test "gate disabled: preserves pilotfish artifacts coexisting in the same agents dir" {
    seed_deployed_home
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$REPO_ROOT/configs/claude/agents"
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"

    ENABLE_DEVPANEL=false run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success

    [ ! -f "$HOME_DIR/agents/developer.md" ]   # devpanel gone
    [ ! -f "$HOME_DIR/agents/.devpanel" ]
    [ -f "$HOME_DIR/agents/scout.md" ]         # pilotfish survives
    [ -f "$HOME_DIR/agents/.pilotfish" ]
    [ -d "$HOME_DIR/agents" ]                  # dir kept (pilotfish still owns content)
}

@test "gate disabled: preserves a user-authored agent that coexists in the dir" {
    seed_deployed_home
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    echo "my custom agent" > "$HOME_DIR/agents/my-agent.md"

    ENABLE_DEVPANEL=false run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success

    [ -f "$HOME_DIR/agents/my-agent.md" ]
    assert_equal "$(cat "$HOME_DIR/agents/my-agent.md")" "my custom agent"
    [ ! -f "$HOME_DIR/agents/developer.md" ]
    [ ! -f "$HOME_DIR/agents/.devpanel" ]
    [ -d "$HOME_DIR/agents" ]
}

@test "gate disabled with unrelated foreign agents dir: leaves it alone (no marker)" {
    mkdir -p "$HOME_DIR/agents"
    echo "user agent" > "$HOME_DIR/agents/my-own.md"
    ENABLE_DEVPANEL=false run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/my-own.md" ]
}

@test "gate disabled does NOT clobber a same-named user agent lacking the marker" {
    mkdir -p "$HOME_DIR/agents"
    echo "user's own developer notes" > "$HOME_DIR/agents/developer.md"
    ENABLE_DEVPANEL=false run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/developer.md" ]
    assert_equal "$(cat "$HOME_DIR/agents/developer.md")" "user's own developer notes"
}

@test "re-enable after a disable that left a coexisting user agent: succeeds, no collision deadlock" {
    seed_deployed_home
    ENABLE_DEVPANEL=true gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    echo "mine" > "$HOME_DIR/agents/my-agent.md"
    ENABLE_DEVPANEL=false gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    [ ! -f "$HOME_DIR/agents/.devpanel" ]

    ENABLE_DEVPANEL=true run check_devpanel_collision "$HOME_DIR"
    assert_success
    ENABLE_DEVPANEL=true run gate_devpanel_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/developer.md" ]
    [ -f "$HOME_DIR/agents/.devpanel" ]
    [ -f "$HOME_DIR/agents/my-agent.md" ]
}

# ---- collision guard --------------------------------------------------------

@test "collision guard: aborts on a foreign agents dir and names the file" {
    mkdir -p "$HOME_DIR/agents"
    echo "user's tester" > "$HOME_DIR/agents/tester.md"
    ENABLE_DEVPANEL=true run check_devpanel_collision "$HOME_DIR"
    assert_failure
    assert_output --partial "tester.md"
    assert_equal "$(cat "$HOME_DIR/agents/tester.md")" "user's tester"
}

@test "collision guard: a differently-named user agent does NOT block enabling" {
    mkdir -p "$HOME_DIR/agents"
    echo "user agent" > "$HOME_DIR/agents/my-agent.md"
    ENABLE_DEVPANEL=true run check_devpanel_collision "$HOME_DIR"
    assert_success
}

@test "collision guard: passes for a Manifest-owned agents dir (marker present)" {
    mkdir -p "$HOME_DIR/agents"
    echo "user's tester" > "$HOME_DIR/agents/tester.md"
    : > "$HOME_DIR/agents/.devpanel"
    ENABLE_DEVPANEL=true run check_devpanel_collision "$HOME_DIR"
    assert_success
}

@test "collision guard: no-op when devpanel is disabled" {
    mkdir -p "$HOME_DIR/agents"
    echo x > "$HOME_DIR/agents/foreign.md"
    ENABLE_DEVPANEL=false run check_devpanel_collision "$HOME_DIR"
    assert_success
}

@test "collision guard: passes when agents dir does not exist" {
    ENABLE_DEVPANEL=true run check_devpanel_collision "$HOME_DIR"
    assert_success
}

# ---- source-file invariants -------------------------------------------------

@test "source: exactly five devpanel role-agent files exist" {
    run bash -c "ls '$REPO_ROOT'/configs/claude/agents-devpanel/*.md | wc -l | tr -d ' '"
    assert_output "5"
}

@test "source: every agent model is a built-in alias, never a raw model ID" {
    run bash -c "grep -hE '^model:' '$REPO_ROOT'/configs/claude/agents-devpanel/*.md | grep -vE '^model: (haiku|sonnet|opus)$'"
    assert_output ""
    run bash -c "grep -hE '^model:' '$REPO_ROOT'/configs/claude/agents-devpanel/*.md | grep -c 'claude-'"
    assert_output "0"
}

@test "source: each role file has exactly one model: line" {
    local f n
    for f in "$REPO_ROOT"/configs/claude/agents-devpanel/*.md; do
        n=$(grep -cE '^model:' "$f")
        assert_equal "$n" "1"
    done
}

@test "source: developer never contests critic feedback (behavioral constraint)" {
    run grep -qiF 'never' "$REPO_ROOT/configs/claude/agents-devpanel/developer.md"
    assert_success
}

@test "source: both validators state the APPROVED gate contract" {
    run grep -qF 'APPROVED' "$REPO_ROOT/configs/claude/agents-devpanel/spec-guard.md"
    assert_success
    run grep -qF 'APPROVED' "$REPO_ROOT/configs/claude/agents-devpanel/chaos-engineer.md"
    assert_success
}

@test "source: delegation reference documents the propose/critique/refactor loop and termination condition" {
    ref="$REPO_ROOT/configs/claude/references/devpanel-delegation.md"
    run grep -qiF 'APPROVED' "$ref"
    assert_success
    run grep -qiF 'spec-guard' "$ref"
    assert_success
    run grep -qiF 'chaos-engineer' "$ref"
    assert_success
}

@test "source: the committed orchestration guide does NOT inline the policy" {
    run grep -cF 'devpanel-delegation.md' "$REPO_ROOT/configs/claude/CLAUDE.md"
    assert_output "0"
}

@test "budget: source guide plus BOTH injected pointers (pilotfish + devpanel) stays under 7550" {
    # Worst case a real deploy can hit: both toggles enabled at once, both pointers
    # injected into the same deployed guide. This is a standalone cap (7550), distinct
    # from context_budget.bats' 7400 cap on the committed SOURCE file alone (unaffected —
    # pointers are injected at deploy time, never committed). Measured total is ~7512
    # bytes; if a future pointer edit trips this, trim the pointer line before raising it.
    local cap=7550
    local src_bytes p1_bytes p2_bytes total
    src_bytes=$(wc -c < "$REPO_ROOT/configs/claude/CLAUDE.md")
    p1_bytes=$(printf '%s\n' "$PILOTFISH_POINTER_LINE" | wc -c)
    p2_bytes=$(printf '%s\n' "$DEVPANEL_POINTER_LINE" | wc -c)
    total=$((src_bytes + p1_bytes + p2_bytes))
    [ "$total" -le "$cap" ] || {
        echo "deployed guide would be $total bytes (cap: $cap)" >&2
        false
    }
}
