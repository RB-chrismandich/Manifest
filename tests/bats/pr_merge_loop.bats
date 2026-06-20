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
  admin-check)      echo "${SEAM_ADMIN:-true}" ;;
  protection)       echo "${SEAM_PROT:-enforce_admins=false required_signatures=false merge_queue=false}" ;;
  update-branch)    echo updated ;;
  do-merge)         [ "${SEAM_MERGE_FAIL:-0}" = 1 ] && exit 1 || echo merged ;;
esac
EOF
    chmod +x "$TMP/seam.sh"
    export PR_MERGE_LOOP_GH_CMD="$TMP/seam.sh"

    # loop_lock seam (file-backed) so cmd_tick can acquire/release offline.
    export LOOP_LOCK_DIR="$TMP/locks"
    export SEAM_STATE="$TMP/labels"
    cat > "$TMP/lockseam.sh" <<'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; mkdir -p "$d"; f="$d/$2"
case "$1" in has) [ -f "$f" ] && { echo 0; exit 0; } || exit 1 ;; add) echo 0>"$f";; remove) rm -f "$f";; esac
EOF
    chmod +x "$TMP/lockseam.sh"; export LOOP_LOCK_LABEL_CMD="$TMP/lockseam.sh"

    # verification gate review seam (tunable via SEAM_GATE).
    cat > "$TMP/gateseam.sh" <<'EOF'
#!/usr/bin/env bash
echo "${SEAM_GATE:-{\"tier1\":{\"passed\":true},\"consensus_score\":0.9}}"
EOF
    chmod +x "$TMP/gateseam.sh"; export VERIFICATION_GATE_REVIEW_CMD="$TMP/gateseam.sh"
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

# --- cmd_merge pre-flight (T017) — fail-closed; no real merges (seamed) ---
@test "merge: non-admin -> exit 9 (fail closed)" {
    SEAM_ADMIN=false run "$SCRIPT" merge 5; [ "$status" -eq 9 ]
}
@test "merge: enforce_admins=true -> exit 9" {
    SEAM_PROT="enforce_admins=true required_signatures=false merge_queue=false" run "$SCRIPT" merge 5
    [ "$status" -eq 9 ]
}
@test "merge: required_signatures=true -> exit 9" {
    SEAM_PROT="enforce_admins=false required_signatures=true merge_queue=false" run "$SCRIPT" merge 5
    [ "$status" -eq 9 ]
}
@test "merge: admin + clean protection, dry-run -> exit 0, no actual merge" {
    PR_MERGE_LOOP_APPLY=0 run "$SCRIPT" merge 5
    [ "$status" -eq 0 ]; [[ "$output" == *"dry-run"* ]]
}
@test "merge: admin + clean, apply -> exit 0" {
    PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" merge 5; [ "$status" -eq 0 ]
}
@test "merge: apply + do-merge fails -> exit 2" {
    PR_MERGE_LOOP_APPLY=1 SEAM_MERGE_FAIL=1 run "$SCRIPT" merge 5; [ "$status" -eq 2 ]
}

# --- cmd_tick dispatch (T021) ---
@test "tick: clean PR + gate pass + high consensus -> merge (dry-run)" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]; [[ "$output" == *"merge"* ]]; [[ "$output" == *"dry-run"* ]]
}
@test "tick: gate Tier-1 fail -> hand-human (never merge)" {
    SEAM_GATE='{"tier1":{"passed":false},"consensus_score":0.9}' run "$SCRIPT" tick 5
    [[ "$output" == *"hand-human"* ]]; [[ "$output" != *"merged"* ]]
}
@test "tick: failing checks -> revise (no gate, no merge)" {
    SEAM_BUCKETS="pass fail" run "$SCRIPT" tick 5
    [[ "$output" == *"revise"* ]]
}
@test "tick: a held lock makes the run skip" {
    mkdir -p "$SEAM_STATE"; echo 0 > "$SEAM_STATE/5"   # pre-locked
    run "$SCRIPT" tick 5
    [[ "$output" == *"skip"* ]]
}
