#!/usr/bin/env bats
# Tests for configs/claude/scripts/merge_decision.sh — the pure merge-decision core.
# Contract: specs/361-auto-dev-merge-loop/contracts/merge_decision.md

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/merge_decision.sh"

# Build a signals JSON: a fully-CLEAR/high-consensus base, with $1 (JSON) merged over it.
mk() {
    python3 -c '
import json,sys
base={"checks":"PASS","review_block":False,"pr_review_disposition":"merge","verify":"pass",
      "gate_tier1":"pass","consensus":0.9,"mergeable":"MERGEABLE","merge_state":"CLEAN",
      "hold":False,"revisions_used":0,"max_revisions":3,"reviewer_error":False,"main_ci":"n/a"}
base.update(json.loads(sys.argv[1] or "{}"))
print(json.dumps(base))' "${1:-}"
}
action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }
label()  { python3 -c 'import json,sys;print(json.load(sys.stdin).get("label") or "")'; }

# --- CLI surface ---
@test "--help exits 0 and mentions decide" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]; [[ "$output" == *"decide"* ]]
}
@test "unknown subcommand exits non-zero" {
    run "$SCRIPT" bogus
    [ "$status" -ne 0 ]
}

# --- decision table (one per row, first-match-wins, fail-closed) ---
@test "main_ci red -> halt (overrides everything)" {
    run "$SCRIPT" decide "$(mk '{"main_ci":"red"}')"
    [ "$status" -eq 0 ]; [ "$(echo "$output" | action)" = "halt" ]
}
@test "reviewer_error -> hand-human/needs-human" {
    run "$SCRIPT" decide "$(mk '{"reviewer_error":true}')"
    [ "$(echo "$output" | action)" = "hand-human" ]; [ "$(echo "$output" | label)" = "needs-human" ]
}
@test "gate_tier1 fail -> hand-human (never merge even at high consensus)" {
    run "$SCRIPT" decide "$(mk '{"gate_tier1":"fail","consensus":0.99}')"
    [ "$(echo "$output" | action)" = "hand-human" ]
}
@test "hold -> hand-human/needs-human" {
    run "$SCRIPT" decide "$(mk '{"hold":true}')"
    [ "$(echo "$output" | action)" = "hand-human" ]
}
@test "review_block -> hand-human/needs-human" {
    run "$SCRIPT" decide "$(mk '{"review_block":true}')"
    [ "$(echo "$output" | action)" = "hand-human" ]
}
@test "mergeable CONFLICTING -> hand-human" {
    run "$SCRIPT" decide "$(mk '{"mergeable":"CONFLICTING"}')"
    [ "$(echo "$output" | action)" = "hand-human" ]
}
@test "merge_state DIRTY -> hand-human" {
    run "$SCRIPT" decide "$(mk '{"merge_state":"DIRTY","mergeable":"CONFLICTING"}')"
    [ "$(echo "$output" | action)" = "hand-human" ]
}
@test "merge_state BEHIND (else clean) -> update-branch" {
    run "$SCRIPT" decide "$(mk '{"merge_state":"BEHIND"}')"
    [ "$(echo "$output" | action)" = "update-branch" ]
}
@test "checks FAIL with budget left -> revise" {
    run "$SCRIPT" decide "$(mk '{"checks":"FAIL","revisions_used":1}')"
    [ "$(echo "$output" | action)" = "revise" ]
}
@test "checks FAIL budget exhausted -> hand-human/needs-human" {
    run "$SCRIPT" decide "$(mk '{"checks":"FAIL","revisions_used":3}')"
    [ "$(echo "$output" | action)" = "hand-human" ]; [ "$(echo "$output" | label)" = "needs-human" ]
}
@test "checks PENDING -> wait" {
    run "$SCRIPT" decide "$(mk '{"checks":"PENDING"}')"
    [ "$(echo "$output" | action)" = "wait" ]
}
@test "mergeable UNKNOWN -> wait" {
    run "$SCRIPT" decide "$(mk '{"mergeable":"UNKNOWN","merge_state":"UNKNOWN"}')"
    [ "$(echo "$output" | action)" = "wait" ]
}
@test "checks NO_CHECKS -> hand-human/needs-human (never auto-merge un-CI'd code)" {
    run "$SCRIPT" decide "$(mk '{"checks":"NO_CHECKS"}')"
    [ "$(echo "$output" | action)" = "hand-human" ]; [ "$(echo "$output" | label)" = "needs-human" ]
}
@test "all clear + consensus 0.86 -> merge" {
    run "$SCRIPT" decide "$(mk '{"consensus":0.86}')"
    [ "$(echo "$output" | action)" = "merge" ]
}
@test "all clear + consensus 0.65 -> hand-human/ready-to-merge" {
    run "$SCRIPT" decide "$(mk '{"consensus":0.65}')"
    [ "$(echo "$output" | action)" = "hand-human" ]; [ "$(echo "$output" | label)" = "ready-to-merge" ]
}
@test "all clear + consensus 0.40 -> hand-human/needs-human" {
    run "$SCRIPT" decide "$(mk '{"consensus":0.40}')"
    [ "$(echo "$output" | action)" = "hand-human" ]; [ "$(echo "$output" | label)" = "needs-human" ]
}

# --- invariants ---
@test "INVARIANT (SC-002): no hard-block input ever yields merge" {
    for j in '{"checks":"FAIL"}' '{"checks":"PENDING"}' '{"checks":"NO_CHECKS"}' \
             '{"review_block":true}' '{"hold":true}' '{"gate_tier1":"fail"}' \
             '{"mergeable":"CONFLICTING"}' '{"merge_state":"DIRTY"}' '{"verify":"fail-blocking"}' \
             '{"reviewer_error":true}' '{"main_ci":"red"}' '{"pr_review_disposition":"keep"}'; do
        run "$SCRIPT" decide "$(mk "$j")"
        [ "$(echo "$output" | action)" != "merge" ] || { echo "MERGED on $j"; false; }
    done
}
@test "INVARIANT: malformed JSON -> hand-human (fail closed), exit 0" {
    run "$SCRIPT" decide 'not json{'
    [ "$status" -eq 0 ]; [ "$(echo "$output" | action)" = "hand-human" ]
}
@test "reads signals from stdin too" {
    run bash -c "echo '$(mk '{"consensus":0.9}')' | '$SCRIPT' decide"
    [ "$(echo "$output" | action)" = "merge" ]
}
