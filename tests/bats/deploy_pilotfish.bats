#!/usr/bin/env bats
# Tests for the pilotfish cost-tiered role-agents toggle (spec 481).
# Covers the common.sh gate/collision/pointer helpers plus source-file invariants
# from contracts/{agent-frontmatter,delegation-policy}.md.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SRC_AGENTS="$REPO_ROOT/configs/claude/agents"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_pilotfish.XXXXXX")
    HOME_DIR="$SANDBOX/.claude"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Simulate the post-rsync state. agents/ AND references/pilotfish-delegation.md are
# EXCLUDED from the wholesale rsync (the gate deploys both from source when enabled),
# so the seed sets up only what rsync actually lands: CLAUDE.md + settings.json. Tests
# that need the agents/reference present call the enabled gate, which copies them.
seed_deployed_home() {
    mkdir -p "$HOME_DIR/references"
    # A minimal guide with the anchor the injector uses.
    cat > "$HOME_DIR/CLAUDE.md" <<'EOF'
# Guide

## Reference Index

- `~/.claude/references/antipatterns.md` — guardrail registry.
EOF
    # A settings file that must never be touched (FR-016).
    printf '{"model":"claude-opus-4-8"}\n' > "$HOME_DIR/settings.json"
}

# ---- gate: enabled ---------------------------------------------------------

@test "gate enabled: stamps marker and injects exactly one pointer line" {
    seed_deployed_home
    ENABLE_PILOTFISH=true run gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/.pilotfish" ]
    [ -d "$HOME_DIR/agents" ]
    run grep -cF 'pilotfish-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "1"
}

@test "gate enabled: deploys exactly the six role files + the reference from source (both rsync-excluded)" {
    seed_deployed_home
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    for a in scout.md Explore.md mech-executor.md executor.md verifier.md security-executor.md; do
        [ -f "$HOME_DIR/agents/$a" ]
    done
    run bash -c "ls '$HOME_DIR'/agents/*.md | wc -l | tr -d ' '"
    assert_output "6"
    [ -f "$HOME_DIR/references/pilotfish-delegation.md" ]     # reference gate-deployed too
}

@test "gate enabled: pointer injection is idempotent (no duplicate on re-run)" {
    seed_deployed_home
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    run grep -cF 'pilotfish-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "1"
}

@test "gate enabled: does not touch settings.json (FR-016)" {
    seed_deployed_home
    before="$(cat "$HOME_DIR/settings.json")"
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_equal "$(cat "$HOME_DIR/settings.json")" "$before"
}

# ---- gate: disabled (clean reverse, SC-003) --------------------------------

@test "gate disabled: removes exactly the pilotfish artifacts, nothing else" {
    seed_deployed_home
    # First enable to inject the pointer, then disable.
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    mkdir -p "$HOME_DIR/skills/other"        # unrelated deployed content
    echo keep > "$HOME_DIR/skills/other/x"
    before_settings="$(cat "$HOME_DIR/settings.json")"

    ENABLE_PILOTFISH=false run gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success

    [ ! -d "$HOME_DIR/agents" ]                                   # agents pruned
    [ ! -f "$HOME_DIR/references/pilotfish-delegation.md" ]       # reference pruned
    run grep -cF 'pilotfish-delegation.md' "$HOME_DIR/CLAUDE.md"
    assert_output "0"                                            # pointer removed
    [ -f "$HOME_DIR/skills/other/x" ]                            # unrelated content intact
    assert_equal "$(cat "$HOME_DIR/settings.json")" "$before_settings"
}

@test "gate disabled: preserves a user-authored agent that coexists in the dir (manifest-scoped prune)" {
    seed_deployed_home
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    # A user drops their own agent alongside the pilotfish ones after enabling.
    echo "my custom agent" > "$HOME_DIR/agents/my-agent.md"

    ENABLE_PILOTFISH=false run gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success

    [ -f "$HOME_DIR/agents/my-agent.md" ]                          # user agent survives
    assert_equal "$(cat "$HOME_DIR/agents/my-agent.md")" "my custom agent"
    [ ! -f "$HOME_DIR/agents/scout.md" ]                           # pilotfish agents gone
    [ ! -f "$HOME_DIR/agents/.pilotfish" ]                         # marker gone
    [ -d "$HOME_DIR/agents" ]                                      # dir kept (not empty)
}

@test "gate disabled with unrelated foreign agents dir: leaves it alone (no marker)" {
    mkdir -p "$HOME_DIR/agents"
    echo "user agent" > "$HOME_DIR/agents/my-own.md"    # no .pilotfish marker
    ENABLE_PILOTFISH=false run gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/my-own.md" ]                 # foreign dir untouched
}

@test "gate disabled does NOT clobber a same-named user agent lacking the marker (FR-008 data-loss guard)" {
    # A disabled default bootstrap must never delete a user's ~/.claude/agents/scout.md
    # just because it shares a pilotfish role name. Because agents/ is rsync-excluded and
    # the marker is absent, the disabled prune is skipped entirely.
    mkdir -p "$HOME_DIR/agents"
    echo "user's own scout" > "$HOME_DIR/agents/scout.md"   # collides on name, no marker
    ENABLE_PILOTFISH=false run gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/scout.md" ]
    assert_equal "$(cat "$HOME_DIR/agents/scout.md")" "user's own scout"
}

@test "re-enable after a disable that left a coexisting user agent: succeeds, no collision deadlock" {
    # enable -> user adds my-agent.md -> disable (marker gone, my-agent survives) ->
    # enable again must NOT abort (my-agent is not one of the six) and must redeploy.
    seed_deployed_home
    ENABLE_PILOTFISH=true gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    echo "mine" > "$HOME_DIR/agents/my-agent.md"
    ENABLE_PILOTFISH=false gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    [ ! -f "$HOME_DIR/agents/.pilotfish" ]                       # marker removed on disable

    ENABLE_PILOTFISH=true run check_pilotfish_collision "$HOME_DIR"
    assert_success                                              # no deadlock on re-enable
    ENABLE_PILOTFISH=true run gate_pilotfish_agents "$HOME_DIR" "$SRC_AGENTS"
    assert_success
    [ -f "$HOME_DIR/agents/scout.md" ]                          # pilotfish redeployed
    [ -f "$HOME_DIR/agents/.pilotfish" ]
    [ -f "$HOME_DIR/agents/my-agent.md" ]                       # user agent still there
}

# ---- collision guard (FR-008) ---------------------------------------------

@test "collision guard: aborts on a foreign agents dir and names the file" {
    mkdir -p "$HOME_DIR/agents"
    echo "user's scout" > "$HOME_DIR/agents/scout.md"   # foreign, no marker
    ENABLE_PILOTFISH=true run check_pilotfish_collision "$HOME_DIR"
    assert_failure
    assert_output --partial "scout.md"
    # touched nothing:
    assert_equal "$(cat "$HOME_DIR/agents/scout.md")" "user's scout"
}

@test "collision guard: a differently-named user agent does NOT block enabling" {
    mkdir -p "$HOME_DIR/agents"
    echo "user agent" > "$HOME_DIR/agents/my-agent.md"  # not one of the six, no marker
    ENABLE_PILOTFISH=true run check_pilotfish_collision "$HOME_DIR"
    assert_success
}

@test "collision guard: passes for a Manifest-owned agents dir (marker present)" {
    mkdir -p "$HOME_DIR/agents"
    echo "user's scout" > "$HOME_DIR/agents/scout.md"
    : > "$HOME_DIR/agents/.pilotfish"                   # owned
    ENABLE_PILOTFISH=true run check_pilotfish_collision "$HOME_DIR"
    assert_success
}

@test "collision guard: no-op when pilotfish is disabled" {
    mkdir -p "$HOME_DIR/agents"
    echo x > "$HOME_DIR/agents/foreign.md"
    ENABLE_PILOTFISH=false run check_pilotfish_collision "$HOME_DIR"
    assert_success
}

@test "collision guard: passes when agents dir does not exist" {
    ENABLE_PILOTFISH=true run check_pilotfish_collision "$HOME_DIR"
    assert_success
}

# ---- source-file invariants (contracts/agent-frontmatter.md) ---------------

@test "source: exactly six role-agent files exist" {
    run bash -c "ls '$REPO_ROOT'/configs/claude/agents/*.md | wc -l | tr -d ' '"
    assert_output "6"
}

@test "source: every agent model is a built-in alias, never a raw model ID" {
    run bash -c "grep -hE '^model:' '$REPO_ROOT'/configs/claude/agents/*.md | grep -vE '^model: (haiku|sonnet|opus)$'"
    assert_output ""    # no line names anything other than the three built-in aliases
    run bash -c "grep -hE '^model:' '$REPO_ROOT'/configs/claude/agents/*.md | grep -c 'claude-'"
    assert_output "0"   # no raw model IDs
}

@test "source: security-executor is opus; scout and Explore are haiku" {
    run grep -qxF 'model: opus' "$REPO_ROOT/configs/claude/agents/security-executor.md"
    assert_success
    run grep -qxF 'model: haiku' "$REPO_ROOT/configs/claude/agents/scout.md"
    assert_success
    run grep -qxF 'model: haiku' "$REPO_ROOT/configs/claude/agents/Explore.md"
    assert_success
}

@test "source: verifier body states the CONFIRMED/REFUTED contract" {
    run grep -qF 'CONFIRMED' "$REPO_ROOT/configs/claude/agents/verifier.md"
    assert_success
    run grep -qF 'REFUTED' "$REPO_ROOT/configs/claude/agents/verifier.md"
    assert_success
}

# ---- source-file invariants (contracts/delegation-policy.md) ---------------

@test "source: delegation reference carries selective-verify and security-routing rules" {
    ref="$REPO_ROOT/configs/claude/references/pilotfish-delegation.md"
    run grep -qiF 'selective' "$ref"
    assert_success
    run grep -qiF 'security-executor' "$ref"
    assert_success
    run grep -qiF 'MIT' "$ref"           # attribution present (FR-011)
    assert_success
}

@test "re-tier: each role file has exactly one model: line (SC-002 one-line edit)" {
    local f n
    for f in "$REPO_ROOT"/configs/claude/agents/*.md; do
        n=$(grep -cE '^model:' "$f")
        assert_equal "$n" "1"
    done
}

@test "source: the committed orchestration guide does NOT inline the policy (FR-014)" {
    # The pointer is injected at deploy time, not committed to the budget-gated guide.
    run grep -cF 'pilotfish-delegation.md' "$REPO_ROOT/configs/claude/CLAUDE.md"
    assert_output "0"
}

@test "budget: source guide plus the injected pointer stays under the 7400-byte cap (FR-009)" {
    # context_budget.bats gates the pointer-free source; this asserts the DEPLOYED
    # guide (source + injected PILOTFISH_POINTER_LINE + newline) also fits the cap,
    # so enabling pilotfish can never push the always-loaded guide over budget.
    local cap=7400
    local src_bytes ptr_bytes total
    src_bytes=$(wc -c < "$REPO_ROOT/configs/claude/CLAUDE.md")
    ptr_bytes=$(printf '%s\n' "$PILOTFISH_POINTER_LINE" | wc -c)
    total=$((src_bytes + ptr_bytes))
    [ "$total" -le "$cap" ] || {
        echo "deployed guide would be $total bytes (cap: $cap)" >&2
        false
    }
}
