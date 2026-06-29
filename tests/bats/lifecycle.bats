#!/usr/bin/env bats
# Tests for configs/claude/scripts/lifecycle.sh — the codified state-gated lifecycle.
# Contract: specs/365-lifecycle-codification/contracts/lifecycle-cli.md

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/lifecycle.sh"

setup() {
    LIFECYCLE_STATE_DIR="$BATS_TEST_TMPDIR/state"
    export LIFECYCLE_STATE_DIR
}

action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }
field()  { python3 -c "import json,sys;print(json.load(sys.stdin).get('$1') or '')"; }

ALL_BUT_LAST='["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement"]'

# --- CLI surface ---
@test "--help exits 0 and mentions decide (before any state lookup)" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]; [[ "$output" == *"decide"* ]]
}
@test "unknown subcommand exits non-zero" {
    run "$SCRIPT" bogus
    [ "$status" -ne 0 ]
}

# --- decide: pure core, always exit 0, fail-closed ---
@test "decide always exits 0 even on garbage" {
    run "$SCRIPT" decide 'not json at all'
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "decide fail-closed on unknown current_phase" {
    run "$SCRIPT" decide '{"current_phase":"bogus"}'
    [ "$(echo "$output" | action)" = "refuse" ]
}

# --- skip detection ---
@test "agent skip-ahead -> refuse, names first missing prerequisite" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$(echo "$output" | action)" = "refuse" ]
    [ "$(echo "$output" | field missing_prereq)" = "spec_review_product" ]
}
@test "human skip-ahead -> warn (advisory), not refuse" {
    run "$SCRIPT" decide '{"actor_mode":"human","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$(echo "$output" | action)" = "warn" ]
}

# --- gate evaluation per gate_type ---
@test "verdict APPROVED -> allow" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"spec_review_product","completed_phases":["specify","clarify"],"phase_gate":{"gate_type":"verdict","verdict":"APPROVED"}}'
    [ "$(echo "$output" | action)" = "allow" ]
}
@test "verdict BLOCKED -> refuse (agent)" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"spec_review_product","completed_phases":["specify","clarify"],"phase_gate":{"gate_type":"verdict","verdict":"BLOCKED"}}'
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "verdict NEEDS_REVIEW -> warn" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"spec_review_product","completed_phases":["specify","clarify"],"phase_gate":{"gate_type":"verdict","verdict":"NEEDS_REVIEW"}}'
    [ "$(echo "$output" | action)" = "warn" ]
}
@test "runner exit 0 -> allow; exit 2 (EMPTY) -> refuse (missing coverage != pass)" {
    run "$SCRIPT" decide "{\"actor_mode\":\"agent\",\"current_phase\":\"verify\",\"requested_phase\":\"verify\",\"completed_phases\":$ALL_BUT_LAST,\"phase_gate\":{\"gate_type\":\"runner\",\"exit_code\":0}}"
    [ "$(echo "$output" | action)" = "allow" ]
    run "$SCRIPT" decide "{\"actor_mode\":\"agent\",\"current_phase\":\"verify\",\"requested_phase\":\"verify\",\"completed_phases\":$ALL_BUT_LAST,\"phase_gate\":{\"gate_type\":\"runner\",\"exit_code\":2}}"
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "coverage MISSING -> refuse (agent)" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"implement","completed_phases":["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech"],"phase_gate":{"gate_type":"coverage","coverage":"MISSING"}}'
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "artifact present -> allow; missing field -> refuse (fail-closed)" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact","present":true}}'
    [ "$(echo "$output" | action)" = "allow" ]
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact"}}'
    [ "$(echo "$output" | action)" = "refuse" ]
}

# --- gate (non-zero exit for loop callers) ---
@test "gate exits 1 on refuse, 0 on allow, 3 on warn" {
    run "$SCRIPT" gate '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact","present":true}}'
    [ "$status" -eq 0 ]
    run "$SCRIPT" gate '{"actor_mode":"agent","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$status" -eq 1 ]
    run "$SCRIPT" gate '{"actor_mode":"human","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$status" -eq 3 ]
}

# --- state subcommands ---
@test "init creates a track from a Jira key, status reports phase 1" {
    run "$SCRIPT" init PROJ-123
    [ "$status" -eq 0 ]; [[ "$output" == *"jira"* ]]
    run "$SCRIPT" status jira__PROJ-123 --json
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | field current_phase)" = "specify" ]
}
@test "init on unrecognized entry point -> exit 2, no track" {
    run "$SCRIPT" init "just some text"
    [ "$status" -eq 2 ]
}
@test "init is idempotent (re-init does not clobber)" {
    "$SCRIPT" init PROJ-9 >/dev/null
    run "$SCRIPT" init PROJ-9
    [ "$status" -eq 0 ]; [[ "$output" == *"exists"* ]]
}
@test "advance with passing artifact gate moves specify -> clarify and persists" {
    "$SCRIPT" init PROJ-7 >/dev/null
    run "$SCRIPT" advance jira__PROJ-7 --actor agent --gate '{"gate_type":"artifact","present":true}'
    [ "$status" -eq 0 ]; [[ "$output" == *"specify -> clarify"* ]]
    run "$SCRIPT" status jira__PROJ-7 --json
    [ "$(echo "$output" | field current_phase)" = "clarify" ]
}
@test "advance refused (agent) does not change phase" {
    "$SCRIPT" init PROJ-8 >/dev/null
    run "$SCRIPT" advance jira__PROJ-8 --actor agent --gate '{"gate_type":"artifact","present":false}'
    [ "$status" -eq 1 ]
    run "$SCRIPT" status jira__PROJ-8 --json
    [ "$(echo "$output" | field current_phase)" = "specify" ]
}
@test "advance warn (human) holds without --override, proceeds with it" {
    "$SCRIPT" init PROJ-10 >/dev/null
    run "$SCRIPT" advance jira__PROJ-10 --actor human --gate '{"gate_type":"artifact","present":false}'
    [ "$status" -eq 3 ]
    run "$SCRIPT" advance jira__PROJ-10 --actor human --gate '{"gate_type":"artifact","present":false}' --override "known-stub, tracked separately"
    [ "$status" -eq 0 ]
}
@test "regress requires a reason and rewinds the phase" {
    "$SCRIPT" init PROJ-11 >/dev/null
    "$SCRIPT" advance jira__PROJ-11 --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
    run "$SCRIPT" regress jira__PROJ-11 --to specify
    [ "$status" -eq 2 ]
    run "$SCRIPT" regress jira__PROJ-11 --to specify --reason "defect found downstream"
    [ "$status" -eq 0 ]
    run "$SCRIPT" status jira__PROJ-11 --json
    [ "$(echo "$output" | field current_phase)" = "specify" ]
}
@test "status on missing track -> exit 2" {
    run "$SCRIPT" status jira__NOPE-1
    [ "$status" -eq 2 ]
}
