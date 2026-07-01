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
case "$1" in has) [ -f "$f" ] && { echo 0; exit 0; } || exit 1 ;; add) echo > "$f";; remove) rm -f "$f";; esac
EOF
    chmod +x "$TMP/lockseam.sh"; export LOOP_LOCK_LABEL_CMD="$TMP/lockseam.sh"

    # verification gate review seam (tunable via SEAM_GATE).
    cat > "$TMP/gateseam.sh" <<'EOF'
#!/usr/bin/env bash
_d='{"tier1":{"passed":true},"consensus_score":0.9}'; echo "${SEAM_GATE:-$_d}"
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

# --- set-disposition: the reviewing agent records its /pr-review verdict ---

@test "set-disposition writes per-PR state" {
    run "$SCRIPT" set-disposition 42 merge
    [ "$status" -eq 0 ]
    [ "$(cat "$PR_MERGE_LOOP_STATE_DIR/disp_42")" = "merge" ]
}

@test "set-disposition rejects values outside merge|keep|close" {
    run "$SCRIPT" set-disposition 42 shipit
    [ "$status" -ne 0 ]
    [ ! -f "$PR_MERGE_LOOP_STATE_DIR/disp_42" ]
}

@test "signals: recorded disposition overrides the live one" {
    "$SCRIPT" set-disposition 7 merge
    SEAM_DISP=keep run "$SCRIPT" signals 7
    [ "$(echo "$output" | field pr_review_disposition)" = "merge" ]
}

@test "signals: without recorded disposition the live one is used" {
    SEAM_DISP=keep run "$SCRIPT" signals 8
    [ "$(echo "$output" | field pr_review_disposition)" = "keep" ]
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
@test "gitlab: merge fails closed (no auto-merge parity → ready-to-merge + human)" {
    unset PR_MERGE_LOOP_GH_CMD                # exercise the real platform branch
    PR_MERGE_LOOP_PLATFORM=gitlab run "$SCRIPT" merge 5
    [ "$status" -eq 9 ]
}

# --- T026: run loop driver + hard ceiling ---
@test "run: _net passes through and returns command output" {
    run "$SCRIPT" _net echo hi
    [ "$status" -eq 0 ]; [ "$output" = "hi" ]
}

@test "run: ceiling already past -> zero passes, no merge, exit 0" {
    # now-seam: first call (start)=0, every later call huge -> deadline gate trips immediately
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
c="${TMP:?}/nowc"; n=$(( $( [ -f "$c" ] && cat "$c" || echo 0 ) + 1 )); echo "$n" > "$c"
[ "$n" -le 1 ] && echo 0 || echo 999999
EOF
    chmod +x "$TMP/now.sh"
    export PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh" TMP PR_MERGE_LOOP_CEILING_SEC=10 PR_MERGE_LOOP_POLL_SEC=0
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [[ "$output" != *"merged"* ]]
}

@test "run: fully-idle passes increment empty-run and stop at 5" {
    export SEAM_LIST='[]' PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "5" ]
}

@test "run: an in-flight (waiting) PR resets the empty-run counter" {
    "$SCRIPT" empty-run incr; "$SCRIPT" empty-run incr; "$SCRIPT" empty-run incr; "$SCRIPT" empty-run incr
    [ "$("$SCRIPT" empty-run get)" = "4" ]
    # now-seam: plenty of zeros (>=1 pass) then sticky-huge to exit
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
c="${TMP:?}/nowc"; n=$(( $( [ -f "$c" ] && cat "$c" || echo 0 ) + 1 )); echo "$n" > "$c"
[ "$n" -le 8 ] && echo 0 || echo 999999
EOF
    chmod +x "$TMP/now.sh"
    export PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh" TMP PR_MERGE_LOOP_CEILING_SEC=10 PR_MERGE_LOOP_POLL_SEC=0
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]' SEAM_BUCKETS="pending"
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "0" ]
}

@test "run: halt action propagates exit 11" {
    # gate passes + clean signals -> merge; force post-merge main RED so tick returns halt
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_APPLY=1 SEAM_MERGE_FAIL=0 PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    # post-merge-check reads gh api directly; seam it to red via a check-runs override
    cat > "$TMP/pmc.sh" <<'EOF'
#!/usr/bin/env bash
echo '["failure"]'
EOF
    chmod +x "$TMP/pmc.sh"
    export PR_MERGE_LOOP_POSTMERGE_CMD="$TMP/pmc.sh"
    run "$SCRIPT" run
    [ "$status" -eq 11 ]
}

# --- T004: real review-thread accessor (fail-closed, allowlist-aware) ---
THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[%s]}}}}}'

@test "threads: unresolved human thread -> count 1" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "1" ]
}
@test "threads: unresolved BOT thread is advisory -> count 0" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"coderabbitai"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "0" ]
}
@test "threads: resolved thread -> count 0" {
    node='{"isResolved":true,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "0" ]
}
@test "threads: outdated unresolved thread -> count 0" {
    node='{"isResolved":false,"isOutdated":true,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "0" ]
}
@test "threads: malformed payload fails closed -> count 1" {
    PR_MERGE_LOOP_THREADS_JSON="not json at all" run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "1" ]
}
@test "threads: missing nodes key fails closed -> count 1" {
    PR_MERGE_LOOP_THREADS_JSON='{"data":{"repository":{"pullRequest":{}}}}' run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "1" ]
}

# --- T011: address-cycle increments revisions + budget exhaustion -> hand-human ---
@test "address-cycle increments revisions_used" {
    "$SCRIPT" address-cycle 5
    [ "$(cat "$PR_MERGE_LOOP_STATE_DIR/rev_5")" = "1" ]
    "$SCRIPT" address-cycle 5
    [ "$(cat "$PR_MERGE_LOOP_STATE_DIR/rev_5")" = "2" ]
}
@test "address-cycle: under budget with failing checks -> revise" {
    "$SCRIPT" address-cycle 5    # revisions_used=1
    sig="$(MAX_REVISIONS=3 SEAM_BUCKETS="pass fail" "$SCRIPT" signals 5)"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "revise" ]
}
@test "address-cycle: at budget with failing checks -> hand-human + needs-human" {
    "$SCRIPT" address-cycle 5; "$SCRIPT" address-cycle 5   # revisions_used=2
    sig="$(MAX_REVISIONS=2 SEAM_BUCKETS="pass fail" "$SCRIPT" signals 5)"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "hand-human" ]
    [ "$(echo "$output" | python3 -c 'import json,sys;print(json.load(sys.stdin)["label"])')" = "needs-human" ]
}

# --- T039: lifecycle gate before merge (fail-open; blocks tracked PRs with audit drift) ---

mk_lc_seams() {
    # resolver: echoes $LC_TRACK for any pr (empty = not tracked)
    cat > "$TMP/lc_resolve.sh" <<'EOF'
#!/usr/bin/env bash
echo "${LC_TRACK:-}"
EOF
    # gate stub: `audit <track>` exits $LC_AUDIT_RC
    cat > "$TMP/lc_gate.sh" <<'EOF'
#!/usr/bin/env bash
[ "$1" = audit ] && exit "${LC_AUDIT_RC:-0}"
exit 0
EOF
    chmod +x "$TMP/lc_resolve.sh" "$TMP/lc_gate.sh"
    export LIFECYCLE_TRACK_FOR_PR_CMD="$TMP/lc_resolve.sh" LIFECYCLE_GATE_CMD="$TMP/lc_gate.sh"
}

@test "lifecycle gate: no resolver wired -> fail open (exit 0)" {
    run "$SCRIPT" _lifecycle_gate 42
    [ "$status" -eq 0 ]
}
@test "lifecycle gate: PR not tracked (resolver empty) -> fail open (exit 0)" {
    mk_lc_seams; export LC_TRACK=""
    run "$SCRIPT" _lifecycle_gate 42
    [ "$status" -eq 0 ]
}
@test "lifecycle gate: tracked PR with clean audit -> ok (exit 0)" {
    mk_lc_seams; export LC_TRACK="jira__PROJ-1" LC_AUDIT_RC=0
    run "$SCRIPT" _lifecycle_gate 42
    [ "$status" -eq 0 ]
}
@test "lifecycle gate: tracked PR with audit DRIFT -> block (exit 1)" {
    mk_lc_seams; export LC_TRACK="jira__PROJ-1" LC_AUDIT_RC=1
    run "$SCRIPT" _lifecycle_gate 42
    [ "$status" -eq 1 ]
}
