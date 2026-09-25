#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/pr_merge_loop.sh — offline-seamed
# orchestration paths. This bundle copy hard-gates `merge` (always refuses,
# exit 78 — see merge_capability_disabled), so the retired operator copy's
# live-merge tests are gone; the gate itself is covered by the dedicated block
# at the end of this file. Every read-only path (signals/decide/tick-to-gate/
# run) is exercised against the seams below.

SCRIPT="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/pr_merge_loop.sh"
DECIDE="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/merge_decision.sh"

setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/prloop.XXXXXX")
    export PR_MERGE_LOOP_STATE_DIR="$TMP/state"
    # Keep forge XDG state (audit_log.jsonl etc.) inside the sandbox too.
    export XDG_STATE_HOME="$TMP/xdg-state"
    # cmd_signals calls cmd_post_merge_check, which first resolves main HEAD via
    # `git ls-remote origin` — run from a non-repo dir so that lookup fails fast
    # and deterministically offline before the POSTMERGE seam is consulted.
    cd "$TMP" || return 1
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
  hold)             echo "${SEAM_HOLD:-false}" ;;
  author)           echo "${SEAM_AUTHOR:-Copilot}" ;;
  admin-check)      echo "${SEAM_ADMIN:-true}" ;;
  protection)       echo "${SEAM_PROT:-enforce_admins=false required_signatures=false merge_queue=false}" ;;
  update-branch)    echo updated ;;
  do-merge)         [ "${SEAM_MERGE_FAIL:-0}" = 1 ] && exit 1 || echo merged ;;
  headsha)          echo "${SEAM_HEAD:-sha1}" ;;
  basebranch)       echo "${SEAM_BASE:-main}" ;;
  mergecommit)      echo "${SEAM_MERGE_SHA:-mergesha1}" ;;
esac
EOF
    chmod +x "$TMP/seam.sh"
    export PR_MERGE_LOOP_GH_CMD="$TMP/seam.sh"

    # loop_lock seam (file-backed) so cmd_tick can acquire/release offline.
    export LOOP_LOCK_DIR="$TMP/locks"
    export LOOP_LOCK_SETTLE_SEC=0.01 # this suite doesn't exercise the race window itself
    # post-merge-check seam: main CI green by default so cmd_signals reports
    # main_ci=green (a red seam is exported per-test to exercise halt).
    cat > "$TMP/pmc-green.sh" <<'EOF'
#!/usr/bin/env bash
echo '["success"]'
EOF
    chmod +x "$TMP/pmc-green.sh"
    export PR_MERGE_LOOP_POSTMERGE_CMD="$TMP/pmc-green.sh"
    export SEAM_STATE="$TMP/labels"
    # Protocol (matches loop_lock.sh's owner-token lease): <cmd> has|add|remove <pr>
    # [<owner>]; `has` prints "<age>\t<owner>" for the newest lease, exit 0 if any.
    #
    # FIXED-BACKEND SEAM (2026-08-20, Finding 1(a)): `add` SUCCEEDS. Real
    # GitHub `--add-label` only ATTACHES a label that already exists as a repo
    # label — it never creates one — and labels.yml can never pre-provision
    # the dynamic "loop-active:<epoch>:<owner>" lease name (the epoch+owner
    # suffix is unbounded, generated fresh per acquisition). loop_lock.sh's
    # `label_op add` now self-provisions it (`gh label create --force`)
    # immediately before attaching it, so a healthy real backend's add
    # succeeds — model that here by writing a lease-marker file, exactly what
    # a real add followed by `has` reading it back would produce. The dedicated
    # DEGRADED-path tests below use their own rejecting seam (mirroring the
    # vendored copy's "vendored REGRESSION: degraded lease" tests) to cover
    # the case where label creation itself still fails (no permission, API
    # error, etc.) — that remains realistic even after this fix and is exactly
    # what Finding 1(b) requires cmd_tick to report loudly rather than skip.
    cat > "$TMP/lockseam.sh" <<'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; op="$1"; pr="$2"; owner="${3:-}"
pd="$d/$pr"; mkdir -p "$pd"
case "$op" in
  has)
    newest="" ; shopt -s nullglob
    for f in "$pd"/*; do o="$(basename "$f")"; [ -z "$newest" ] || [[ "$o" > "$newest" ]] && newest="$o"; done
    [ -n "$newest" ] || exit 1
    printf '%s\t%s\n' "${SEAM_AGE:-0}" "$newest"
    exit 0 ;;
  add)
    [ -n "$owner" ] || exit 1
    : > "$pd/$owner"
    exit 0 ;;
  remove) [ -n "$owner" ] && rm -f "$pd/$owner"; exit 0 ;;
esac
EOF
    chmod +x "$TMP/lockseam.sh"; export LOOP_LOCK_LABEL_CMD="$TMP/lockseam.sh"

    # DEGRADED-backend seam (Finding 1(b) regression coverage): `add` always
    # rejects, modeling a backend where label creation itself cannot land.
    # Opt in per-test via `LOOP_LOCK_LABEL_CMD="$TMP/lockseam_degraded.sh"`.
    cat > "$TMP/lockseam_degraded.sh" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  has) exit 1 ;;
  add) exit 1 ;;
  remove) exit 0 ;;
esac
EOF
    chmod +x "$TMP/lockseam_degraded.sh"

    # verification gate review seam (tunable via SEAM_GATE).
    cat > "$TMP/gateseam.sh" <<'EOF'
#!/usr/bin/env bash
_d='{"tier1":{"passed":true},"tier2":{"concerns":[]},"verdict":"APPROVED"}'; echo "${SEAM_GATE:-$_d}"
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
# merge — the merge-gate block below covers that path. CONTENDED still yields
# a benign "skip" (exit 0, see "a held lock makes the run skip" below).

@test "tick: gate Tier-1 fail -> hand-human (never merge)" {
    SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}' run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"hand-human"* ]] && [[ "$output" != *"merged"* ]]
}
@test "tick: failing checks -> revise (no gate, no merge)" {
    SEAM_BUCKETS="pass fail" run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"revise"* ]]
}
# --- REGRESSION (Finding 1(b)): CONTENDED stays a benign skip. The DEGRADED
# variant lives in the merge-gate block below — this bundle's cmd_tick treats
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
    # proceed-without-lock path covered in the merge-gate block below.
    mkdir -p "$SEAM_STATE/5"; : > "$SEAM_STATE/5/other-owner" # genuinely held
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *$'\nskip'* ]]
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
    # main_ci=red makes decide() halt the PR (tick prints "halt"), and cmd_run
    # maps halt -> exit 11 on the first pass — no live merge needed now that
    # signals derive main_ci from cmd_post_merge_check directly.
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    cat > "$TMP/pmc-red.sh" <<'EOF'
#!/usr/bin/env bash
echo '["failure"]'
EOF
    chmod +x "$TMP/pmc-red.sh"
    export PR_MERGE_LOOP_POSTMERGE_CMD="$TMP/pmc-red.sh"
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

# =====================================================================
# MERGE HARD GATE (CDDL QA-critic finding): `merge` in this bundle copy always
# refuses (exit 78) — the retired operator copy's live-merge tests are deleted
# above; this block covers the gate itself and the read-only subset.
# =====================================================================

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
# Finding 1(a)'s fix (a healthy backend's `add` now succeeds — the suite-wide
# seam above models that), label creation can still fail for real reasons (no
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
        [[ "$output" == *"automated merge is disabled"* ]] # reached the real dispatch (merge -> hard gate)
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
