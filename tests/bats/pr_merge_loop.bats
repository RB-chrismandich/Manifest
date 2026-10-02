#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/pr_merge_loop.sh — offline-seamed
# orchestration paths. This bundle copy hard-gates `merge` (always refuses,
# exit 78 — see merge_capability_disabled), so the retired operator copy's
# live-merge tests are gone; the gate itself is covered by the dedicated block
# in pr_merge_loop_vendored.bats. This file keeps the read-only paths
# (signals/decide/tick dispatch), threads, address-cycle, and the lifecycle
# gate; the modules below were split out at the 600-line constitution ceiling:
#
#   pr_merge_loop_empty_run.bats  — empty counter + cmd_run driver/ceiling
#   pr_merge_loop_monitor.bats    — provider degrade + gitlab queue monitor
#   pr_merge_loop_fp.bats         — material fingerprinting + transition state
#   pr_merge_loop_vendored.bats   — vendored boundary + merge hard-gate
#
# All modules share the seam harness in
# tests/test_helper/pr_merge_loop_seams.bash.

source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"

setup()    { pr_merge_loop_setup; }
teardown() { pr_merge_loop_teardown; }

@test "--help exits 0" { run "$SCRIPT" --help; [ "$status" -eq 0 ]; }

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
@test "signals: red main CI -> main_ci red and decide halts" {
    cat > "$TMP/pmc-red.sh" <<'EOF'
#!/usr/bin/env bash
echo '["failure"]'
EOF
    chmod +x "$TMP/pmc-red.sh"
    export PR_MERGE_LOOP_POSTMERGE_CMD="$TMP/pmc-red.sh"
    sig="$("$SCRIPT" signals 5)"
    [ "$(echo "$sig" | field main_ci)" = "red" ]
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "halt" ]
}

# --- integration: signals -> merge_decision ---
@test "integration: a clean PR with gate pass injected -> merge" {
    sig="$("$SCRIPT" signals 5)"
    # merge path injects gate_tier1=pass before deciding
    sig="$(echo "$sig" | python3 -c 'import json,sys;d=json.load(sys.stdin);d["gate_tier1"]="pass";print(json.dumps(d))')"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "merge" ]
}
@test "integration: NO_CHECKS never merges even with gate pass" {
    sig="$(SEAM_BUCKETS="" "$SCRIPT" signals 5)"
    sig="$(echo "$sig" | python3 -c 'import json,sys;d=json.load(sys.stdin);d["gate_tier1"]="pass";print(json.dumps(d))')"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" != "merge" ]
}

# --- cmd_tick dispatch (T021) ---
# Note: this bundle's cmd_merge is hard-gated (always refuses, exit 78), so a
# "merge" tick decision resolves to needs-human/hand-human rather than a real
# merge — pr_merge_loop_vendored.bats covers that path. CONTENDED still yields
# a benign "skip" (exit 0, see "a held lock makes the run skip" below).

@test "tick: gate Tier-1 fail -> hand-human and dedupes on second tick" {
    SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}' run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"hand-human"* ]] && [[ "$output" != *"merged"* ]]
    [ -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
    gate_runs_before="$(gate_count)"
    SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}' run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"unchanged"* ]]
    [ "$(gate_count)" = "$gate_runs_before" ]
}
@test "tick: reviewer infrastructure failure degrades and never persists state" {
    SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED","reviewer_error":true}' run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"hand-human"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
}
@test "tick: failing checks -> revise (no gate, no merge)" {
    SEAM_BUCKETS="pass fail" run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"revise"* ]]
}
# --- REGRESSION (Finding 1(b)): CONTENDED stays a benign skip. The DEGRADED
# variant lives in pr_merge_loop_vendored.bats — this bundle's cmd_tick treats
# an unattemptable lease as "proceed without the lock", not the retired
# operator copy's loud exit 12. ---
@test "tick: a held lock makes the run skip (CONTENDED -> benign, exit 0)" {
    # FIX: seed a genuine lease the way the lockseam's `has` op actually reads
    # it — a directory named for the PR containing a file named for the owner
    # token (`$SEAM_STATE/<pr>/<owner>`) — not a bare file at
    # `$SEAM_STATE/<pr>`. The old bare-file form made the seam's internal
    # `mkdir -p "$pd"` fail (path existed as a file), so `has` silently
    # reported "no lease" for the WRONG reason; the test still passed, but only
    # because that mkdir failure cascaded into a *different* skip path ("lock
    # lost after add" inside cmd_acquire, itself another exit-1 code path) —
    # not because a held lease was ever actually modeled. This form is read
    # correctly and blocks via the real "already locked" path (held_active),
    # independent of whether `add` is faithful or permissive.
    #
    # Finding 1(b): CONTENDED is still a benign skip, distinct from the DEGRADED
    # proceed-without-lock path covered in pr_merge_loop_vendored.bats.
    mkdir -p "$SEAM_STATE/5"; : > "$SEAM_STATE/5/other-owner" # genuinely held
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *$'\nskip'* ]]
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

# --- SECURITY finding 3: a human objection LATER in a bot-started thread must
# still block; only checking the first comment silently dropped it. ---
@test "threads: bot-started thread with a LATER human objection -> count 1" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"coderabbitai"}},{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "1" ]
}
@test "threads: all-bot multi-comment thread stays advisory -> count 0" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"coderabbitai"}},{"author":{"login":"Copilot"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "0" ]
}
@test "threads: comment list truncated past the page cap -> fails closed (counts as blocking)" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":true},"nodes":[{"author":{"login":"coderabbitai"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "1" ]
}
@test "threads: two NDJSON pages accumulate across thread-level pagination" {
    # gh_threads_raw's seam prints PR_MERGE_LOOP_THREADS_JSON verbatim (+ a
    # trailing newline) — embedding a real newline between two page objects
    # exercises the SAME multi-line accumulation path a real paginated fetch
    # produces, without needing to fake gh api's cursor protocol.
    page1='{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}]}}}}}'
    page2='{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"another-human"}}]}}]}}}}}'
    PR_MERGE_LOOP_THREADS_JSON="${page1}
${page2}" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "2" ]
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
