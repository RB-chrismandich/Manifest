#!/usr/bin/env bats
# Behavioural audit: subagent_breakdown.py --audit.
#
# This is the check that makes the hook, the policy doc and the skill fix
# durable. T7/T8 read command_config.yml against SKILL.md prose; they cannot
# fail when a dispatch actually runs on Opus. This one reads the
# agent-<id>.meta.json sidecar (model REQUESTED) against the transcript (model
# SERVED), so it observes behaviour rather than documentation — which is the
# whole reason 11,000 inherited premium requests could accumulate under a policy
# that was already written down.

bats_require_minimum_version 1.5.0

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    AUDIT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)/subagent_breakdown.py"
    ROOT="$BATS_TEST_TMPDIR/projects"
    AGENTS="$BATS_TEST_TMPDIR/proj/.claude/agents"
    mkdir -p "$AGENTS"
    export CLAUDE_PROJECT_DIR="$BATS_TEST_TMPDIR/proj"
    SINCE="2026-01-01T00:00:00Z"
}

# dispatch <id> <agent-type> <requested-model|-> <served-model> [workflow]
# Writes the sidecar + a one-assistant-line transcript, mirroring the real layout.
dispatch() {
    local id="$1" atype="$2" requested="$3" served="$4" wf="${5:-}"
    local dir="$ROOT/someproject/session-1/subagents"
    [ -n "$wf" ] && dir="$dir/workflows/wf_test"
    mkdir -p "$dir"
    if [ "$requested" = "-" ]; then
        printf '{"agentType":"%s","description":"d","toolUseId":"t","spawnDepth":1}\n' \
            "$atype" > "$dir/agent-$id.meta.json"
    else
        printf '{"agentType":"%s","description":"d","toolUseId":"t","spawnDepth":1,"model":"%s"}\n' \
            "$atype" "$requested" > "$dir/agent-$id.meta.json"
    fi
    printf '{"type":"assistant","timestamp":"2026-07-26T12:00:00Z","requestId":"r-%s","isSidechain":true,"message":{"model":"%s","usage":{"input_tokens":1,"output_tokens":1}}}\n' \
        "$id" "$served" > "$dir/agent-$id.jsonl"
}

audit() {
    run python3 "$AUDIT" --audit --root "$ROOT" --since "$SINCE" "$@"
}

@test "--help exits 0 and prints Usage" {
    run python3 "$AUDIT" --help
    assert_success
    assert_output --partial "Usage"
}

@test "an inherited premium dispatch is a violation" {
    dispatch a1 general-purpose - claude-opus-5
    audit
    assert_failure
    assert_output --partial "INHERITED PREMIUM DISPATCHES: 1"
}

@test "an explicitly requested premium model is a permitted exception" {
    dispatch a1 general-purpose opus claude-opus-5
    audit
    assert_success
    assert_output --partial "INHERITED PREMIUM DISPATCHES: 0"
}

@test "an inherited NON-premium dispatch is not a violation" {
    dispatch a1 general-purpose - claude-sonnet-5
    audit
    assert_success
}

@test "a frontmatter-pinned agent is not a violation (the hook must skip it)" {
    printf -- '---\nname: verifier\nmodel: opus\n---\nb\n' > "$AGENTS/verifier.md"
    dispatch a1 verifier - claude-opus-5
    audit
    assert_success
    assert_output --partial "frontmatter:opus"
}

@test "Fable counts as premium (derived from the price table, not a name list)" {
    dispatch a1 general-purpose - claude-fable-5
    audit
    assert_failure
}

@test "the workflow channel is reported but not audited by default" {
    dispatch w1 workflow-subagent - claude-opus-5 workflow
    audit
    assert_success
    assert_output --partial "NOT AUDITED HERE"
    assert_output --partial "1 inherited-premium"
}

@test "--channel workflow audits the workflow channel instead" {
    dispatch w1 workflow-subagent - claude-opus-5 workflow
    audit --channel workflow
    assert_failure
}

@test "--channel all audits both" {
    dispatch a1 general-purpose - claude-sonnet-5
    dispatch w1 workflow-subagent - claude-opus-5 workflow
    audit --channel all
    assert_failure
}

@test "a clean corpus exits 0 with an explicit OK" {
    dispatch a1 general-purpose sonnet claude-sonnet-5
    dispatch a2 general-purpose haiku claude-haiku-4-5
    audit
    assert_success
    assert_output --partial "OK — no inherited premium-model dispatches"
}

@test "fork is not a violation (it ignores model by design; no fix exists)" {
    dispatch f1 fork - claude-opus-5
    audit
    assert_success
    assert_output --partial "unpinnable premium"
    assert_output --partial "INHERITED PREMIUM DISPATCHES: 0"
}

@test "an unpriced model is surfaced, never silently passed" {
    dispatch a1 general-purpose - claude-unknown-9
    audit
    assert_output --partial "unclassified models"
}

@test "the violation names the offending dispatch" {
    dispatch a1 pr-review-toolkit:thing - claude-opus-5
    audit
    assert_failure
    assert_output --partial "pr-review-toolkit:thing"
    assert_output --partial "agent-a1.meta.json"
}

@test "dispatches before --since are outside the window" {
    dispatch a1 general-purpose - claude-opus-5
    run python3 "$AUDIT" --audit --root "$ROOT" --since "2027-01-01T00:00:00Z"
    assert_success
}

@test "a missing transcript root is an error, not a false pass" {
    run python3 "$AUDIT" --audit --root "$BATS_TEST_TMPDIR/nope" --since "$SINCE"
    assert_failure
    assert_output --partial "transcript root not found"
}

@test "--audit with no --since and no stamp is an error, not a silent all-time scan" {
    dispatch a1 general-purpose - claude-opus-5
    run python3 "$AUDIT" --audit --root "$ROOT" --stamp "$BATS_TEST_TMPDIR/absent-stamp"
    assert_failure
    assert_output --partial "no --since"
}

@test "--since defaults to deployed_at in the deploy stamp" {
    dispatch a1 general-purpose - claude-opus-5
    printf 'dirty=false\ndeployed_at=2026-01-01T00:00:00Z\n' > "$BATS_TEST_TMPDIR/stamp"
    run python3 "$AUDIT" --audit --root "$ROOT" --stamp "$BATS_TEST_TMPDIR/stamp"
    assert_failure
    assert_output --partial "since=2026-01-01T00:00:00+00:00"
}
