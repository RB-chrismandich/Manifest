#!/usr/bin/env bats
# Tests for the vendored boundary of
# plugins/manifest-forge/runtime/bin/pr_merge_loop.sh — shared
# fingerprint/race/idle behavior is repeated at this boundary, and its
# structural merge gate (cmd_merge refuses unconditionally, exit 78) is
# covered here: gate under APPLY=0/1, admin-eligible PRs, the cmd_tick merge
# branch, degraded-vs-held lease regression, and the unaffected read-only
# subset.
# Shares the offline seam harness in tests/test_helper/pr_merge_loop_seams.bash
# (split out of pr_merge_loop.bats at the 600-line ceiling — see that file's
# header for the module map).

source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"

setup()    { pr_merge_loop_setup; }
teardown() { pr_merge_loop_teardown; }

VENDORED="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/pr_merge_loop.sh"
VENDORED_DECIDE="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/merge_decision.sh"

# =====================================================================
# VENDORED COPY (plugins/manifest-forge/runtime/bin/pr_merge_loop.sh) —
# shared fingerprint/race/idle behavior is repeated at this boundary.
# Its structural merge gate remains intentionally different and is tested
# independently below.
# =====================================================================

@test "vendored: identical material skips repeated review and label mutation" {
    PR_MERGE_LOOP_APPLY=1 run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"automated merge is disabled"* ]]
    [ "$(gate_count)" = "1" ] && [ "$(call_count add-label)" = "1" ]

    PR_MERGE_LOOP_APPLY=1 run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"unchanged"* ]]
    [ "$(gate_count)" = "1" ] && [ "$(call_count add-label)" = "1" ]
}

@test "vendored: a head transition resumes exactly once" {
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    printf 'sha2\n' > "$SEAM_HEAD_DIR/5"
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    [ "$(gate_count)" = "2" ]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1
    [ "$(gate_count)" = "2" ]
}

@test "vendored: CI rerun, new review, and thread resolution each resume once" {
    export SEAM_BUCKETS="pending"
    export SEAM_FP_CHECKS='[{"name":"ci","bucket":"pending","state":"IN_PROGRESS","link":"https://checks.invalid/1","startedAt":"2026-09-19T00:00:00Z","completedAt":null}]'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"wait"* ]]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_CHECKS='[{"name":"ci","bucket":"pending","state":"IN_PROGRESS","link":"https://checks.invalid/2","startedAt":"2026-09-19T01:00:00Z","completedAt":null}]'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"wait"* ]] && [[ "$output" != *"unchanged"* ]]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_LATEST_REVIEWS='[{"id":"R1","state":"APPROVED","submittedAt":"2026-09-19T02:00:00Z"}]'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"2026-09-19T03:00:00Z","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"2026-09-19T03:00:00Z"}]}}]}}}}}'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":true,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"2026-09-19T03:00:00Z","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"2026-09-19T03:00:00Z"}]}}]}}}}}'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    run "$VENDORED" tick 5
    [[ "$output" == *"unchanged"* ]]
}

@test "vendored: repositories namespace same-number PR state" {
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/one"}'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ]
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/two"}'
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    python3 - "$PR_MERGE_LOOP_STATE_DIR" <<'PY'
import glob
import os
import sys

assert len(glob.glob(os.path.join(sys.argv[1], "fp_*_5.json"))) == 2
PY
}

@test "vendored: observation and reviewer failures never create transition state" {
    SEAM_FP_FAIL=fp-checks run "$VENDORED" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"observation"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]

    SEAM_GATE_FAIL=1 run "$VENDORED" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"review"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
}

@test "vendored: second worker rechecks state after acquiring the lease" {
    run "$VENDORED" tick 5
    [ "$status" -eq 0 ]
    state="$(fingerprint_state)"
    cp "$state" "$TMP/raced-state"
    rm "$state"
    export RACE_STATE="$TMP/raced-state" RACE_DEST="$state"
    make_race_lock_seam
    : > "$SEAM_GATE_LOG"

    LOOP_LOCK_LABEL_CMD="$TMP/race-lockseam.sh" run "$VENDORED" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"unchanged"* ]]
    [ "$(gate_count)" = "0" ]
}

@test "vendored: run handles a transition once and stops after five idle passes" {
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$VENDORED" run
    [ "$status" -eq 0 ] && [[ "$output" == *"5 consecutive empty passes"* ]]
    [ "$(gate_count)" = "1" ]
    # 13 = 3 transition fp-views (run + tick re-read + post-dispatch) + 5 idle
    # passes × 2 (run collect + unchanged re-observe for the in-flight lookup).
    [ "$(call_count fp-view)" = "13" ]
    [ "$("$VENDORED" empty-run get)" = "5" ]
}

@test "vendored: failed update action is degraded and leaves no transition state" {
    SEAM_MRG="MERGEABLE BEHIND" SEAM_UPDATE_FAIL=1 run "$VENDORED" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"update-branch action failed"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
}

@test "vendored: merge is hard-gated regardless of PR_MERGE_LOOP_APPLY (dry-run)" {
    PR_MERGE_LOOP_APPLY=0 run "$SCRIPT" merge 5
    [ "$status" -eq 78 ]
    [[ "$output" == *"automated merge is disabled"* ]] || return 1
    [[ "$output" == *"marketplace-restructure-design.md"* ]] || return 1
    [[ "$output" != *"dry-run"* ]] # no preview text — merge never even previews
}
@test "vendored: merge is hard-gated regardless of PR_MERGE_LOOP_APPLY (apply=1)" {
    # The exact scenario from the task's direct-attempt check: APPLY=1 must NOT
    # re-enable it — the gate is not an env toggle.
    PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" merge 5
    [ "$status" -eq 78 ]
    [[ "$output" == *"automated merge is disabled"* ]]
}
@test "vendored: an admin-eligible, checks-green PR still cannot merge" {
    # Would have cleared every pre-flight check on the retired operator copy —
    # confirms the gate does not depend on any signal, it is unconditional.
    SEAM_ADMIN=true SEAM_PROT="enforce_admins=false required_signatures=false merge_queue=false" \
        PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" merge 5
    [ "$status" -eq 78 ]
}
@test "vendored: cmd_tick's merge branch also refuses (never calls gh do-merge)" {
    # NOTE: chained with && (not bare newline-/semicolon-separated [[ ]]) — under
    # bash 3.2 (macOS system /bin/bash, still first on PATH in some environments)
    # a failing [[ ]] that is not the function's last statement and not tested
    # by &&/if/while does NOT trigger errexit, so an earlier weaker form of this
    # assertion would have stayed green even if tick died at the lock instead of
    # reaching the merge gate — the trailing "!= *merged*" clause alone (true
    # for a bare "skip" too) would have carried the whole test either way.
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && \
        [[ "$output" == *"automated merge is disabled"* ]] && \
        [[ "$output" != *"merged"* ]]
}
# --- REGRESSION (2026-08-20, restoring proportionate tick/run): even after
# Finding 1(a)'s fix (a healthy backend's `add` now succeeds — the shared
# lockseam in pr_merge_loop_seams.bash models that), label creation can still fail for real reasons (no
# permission, API error) — the dedicated degraded seam models THAT. Prove
# cmd_tick still does useful work in that DEGRADED case, and still declines
# when the lease is GENUINELY held. ---
@test "vendored REGRESSION: degraded lease (backend rejects add) — tick still dispatches real work, not skip" {
    LOOP_LOCK_LABEL_CMD="$TMP/lockseam_degraded.sh" run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && \
        [[ "$output" == *"cross-host lease unavailable"* ]] && \
        [[ "$output" == *"proceeding WITHOUT it"* ]] && \
        [[ "$output" != *"locked — skipping"* ]] && \
        [[ "$output" != *$'\nskip'* ]] && \
        [[ "$output" == *"automated merge is disabled"* ]] || return 1 # reached the real dispatch (merge -> hard gate)
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
}
@test "vendored REGRESSION: genuinely held lease (a live, non-stale lease owned by someone else) — tick still declines" {
    # Seed a real lease via the SAME (pr)/(owner-file) layout `has` reads —
    # independent of `add`'s behaviour, since held_active() is checked BEFORE
    # any add is attempted (loop_lock.sh:133-136).
    mkdir -p "$SEAM_STATE/5"; : > "$SEAM_STATE/5/other-owner"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && \
        [[ "$output" == *"locked — skipping"* ]] && \
        [[ "$output" == *$'\nskip'* ]] && \
        [[ "$output" != *"automated merge is disabled"* ]] # never reached dispatch — correctly blocked
}
@test "vendored: read-only subset unaffected — list-managed still works" {
    export SEAM_LIST='[{"number":1,"author":{"login":"Copilot","__typename":"Bot"}}]'
    run "$SCRIPT" list-managed
    [ "$status" -eq 0 ]
    echo "$output" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert [p["number"] for p in d]==[1], d'
}
@test "vendored: read-only subset unaffected — signals still works" {
    SEAM_BUCKETS="pass pass" run "$SCRIPT" signals 5
    [ "$(echo "$output" | field checks)" = "PASS" ]
}
@test "vendored: read-only subset unaffected — decide still reaches a merge verdict (decision layer, not the gated sink)" {
    sig="$("$SCRIPT" signals 5)"
    sig="$(echo "$sig" | python3 -c 'import json,sys;d=json.load(sys.stdin);d["gate_tier1"]="pass";print(json.dumps(d))')"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "merge" ] # merge_decision.sh is unmodified/ungated; the sink (cmd_merge) is what refuses
}
@test "vendored: --help exits 0 and documents the gate" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"HARD-GATED"* ]]
}
