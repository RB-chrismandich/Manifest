#!/usr/bin/env bats
# Tests for configs/claude/scripts/pr_merge_loop.sh — offline-seamed orchestration paths.

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/pr_merge_loop.sh"
DECIDE="$BATS_TEST_DIRNAME/../../configs/claude/scripts/merge_decision.sh"

setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/prloop.XXXXXX")
    export PR_MERGE_LOOP_STATE_DIR="$TMP/state"
    # Seam: <op> <pr>. Values come from per-op env so each test tunes them.
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  list)             echo "${SEAM_LIST:-[]}" ;;
  checks)           printf '%s\n' ${SEAM_BUCKETS-pass} ;;
  reviewdecision)   echo "${SEAM_RD:-APPROVED}" ;;
  unresolved-human) echo "${SEAM_UH:-0}" ;;
  disposition)      echo "${SEAM_DISP:-merge}" ;;
  mergeable)        echo "${SEAM_MRG:-MERGEABLE CLEAN}" ;;
  verify)           echo "${SEAM_VERIFY:-pass}" ;;
  hold)             echo "${SEAM_HOLD:-false}" ;;
  author)           echo "${SEAM_AUTHOR:-Copilot}" ;;
esac
EOF
    chmod +x "$TMP/seam.sh"
    export PR_MERGE_LOOP_GH_CMD="$TMP/seam.sh"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

field() { python3 -c "import json,sys;print(json.load(sys.stdin)[\"$1\"])"; }
action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }

@test "--help exits 0" { run "$SCRIPT" --help; [ "$status" -eq 0 ]; }

# --- empty-run counter ---
@test "empty-run get/incr/reset" {
    run "$SCRIPT" empty-run get;   [ "$output" = "0" ]
    run "$SCRIPT" empty-run incr;  [ "$output" = "1" ]
    run "$SCRIPT" empty-run incr;  [ "$output" = "2" ]
    run "$SCRIPT" empty-run reset; [ "$output" = "0" ]
    run "$SCRIPT" empty-run get;   [ "$output" = "0" ]
}

# --- list-managed allowlist filter (FR-013) ---
@test "list-managed keeps automation authors, drops humans" {
    export SEAM_LIST='[{"number":1,"author":{"login":"Copilot","__typename":"Bot"}},{"number":2,"author":{"login":"some-human"}}]'
    run "$SCRIPT" list-managed
    [ "$status" -eq 0 ]
    echo "$output" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert [p["number"] for p in d]==[1], d'
}

# --- signals classification ---
@test "signals: clean PR classifies PASS + not blocked" {
    SEAM_BUCKETS="pass pass" run "$SCRIPT" signals 5
    [ "$(echo "$output" | field checks)" = "PASS" ]
    [ "$(echo "$output" | field review_block)" = "False" ]
}
@test "signals: a failing bucket -> FAIL" {
    SEAM_BUCKETS="pass fail" run "$SCRIPT" signals 5
    [ "$(echo "$output" | field checks)" = "FAIL" ]
}
@test "signals: empty buckets -> NO_CHECKS" {
    SEAM_BUCKETS="" run "$SCRIPT" signals 5
    [ "$(echo "$output" | field checks)" = "NO_CHECKS" ]
}
@test "signals: human CHANGES_REQUESTED -> review_block true" {
    SEAM_RD="CHANGES_REQUESTED" run "$SCRIPT" signals 5
    [ "$(echo "$output" | field review_block)" = "True" ]
}
@test "signals: unresolved human thread -> review_block true" {
    SEAM_UH="2" run "$SCRIPT" signals 5
    [ "$(echo "$output" | field review_block)" = "True" ]
}
@test "signals: gate fields are null (populated lazily by merge path)" {
    run "$SCRIPT" signals 5
    [ "$(echo "$output" | field gate_tier1)" = "None" ]
}

# --- integration: signals -> merge_decision ---
@test "integration: a clean PR with gate+consensus injected -> merge" {
    sig="$("$SCRIPT" signals 5)"
    # merge path injects gate_tier1=pass + consensus high before deciding
    sig="$(echo "$sig" | python3 -c 'import json,sys;d=json.load(sys.stdin);d["gate_tier1"]="pass";d["consensus"]=0.9;print(json.dumps(d))')"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "merge" ]
}
@test "integration: NO_CHECKS never merges even with gate pass + high consensus" {
    sig="$(SEAM_BUCKETS="" "$SCRIPT" signals 5)"
    sig="$(echo "$sig" | python3 -c 'import json,sys;d=json.load(sys.stdin);d["gate_tier1"]="pass";d["consensus"]=0.99;print(json.dumps(d))')"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" != "merge" ]
}
