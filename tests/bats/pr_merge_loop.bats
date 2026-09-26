#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/pr_merge_loop.sh — offline-seamed
# orchestration paths. This bundle copy hard-gates `merge` (always refuses,
# exit 78 — see merge_capability_disabled), so the retired operator copy's
# live-merge tests are gone; the gate itself is covered by the dedicated block
# at the end of this file. Every read-only path (signals/decide/tick-to-gate/
# run) plus state-driven fingerprint polling is exercised against the seams below.

SCRIPT="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/pr_merge_loop.sh"
DECIDE="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/merge_decision.sh"
VENDORED="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/pr_merge_loop.sh"
VENDORED_DECIDE="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/merge_decision.sh"

setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/prloop.XXXXXX")
    export TMP PR_MERGE_LOOP_STATE_DIR="$TMP/state"
    # Keep forge XDG state (audit_log.jsonl etc.) inside the sandbox too.
    export XDG_STATE_HOME="$TMP/xdg-state"
    export SEAM_CALL_LOG="$TMP/gh-calls" SEAM_GATE_LOG="$TMP/gate-calls"
    export SEAM_LABEL_LOG="$TMP/label-calls" SEAM_HEAD_DIR="$TMP/heads"
    mkdir -p "$SEAM_HEAD_DIR"
    : > "$SEAM_CALL_LOG"
    : > "$SEAM_GATE_LOG"
    : > "$SEAM_LABEL_LOG"

    # cmd_signals calls cmd_post_merge_check, which first resolves main HEAD via
    # `git ls-remote origin` — run from a non-repo dir so that lookup fails fast
    # and deterministically offline before the POSTMERGE seam is consulted.
    cd "$TMP" || return 1

    # Host seam: <op> <pr>. Fingerprint observations are complete by default and
    # can be replaced independently to model a single material transition.
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
op="$1"; pr="${2:-}"
printf '%s %s\n' "$op" "$pr" >> "${SEAM_CALL_LOG:?}"
if [[ "${SEAM_FP_FAIL:-}" == "$op" || "${SEAM_FP_FAIL:-}" == "${op#fp-}" ]]; then
  exit 71
fi
case "$op" in
  fp-scope)
    if [[ -n "${SEAM_SCOPE:-}" ]]; then
      printf '%s\n' "$SEAM_SCOPE"
    else
      printf '%s\n' '{"host":"github.com","owner_repo":"acme/widgets"}'
    fi ;;
  fp-view)
    if [[ -n "${SEAM_FP_VIEW:-}" ]]; then
      printf '%s\n' "$SEAM_FP_VIEW"
    else
      python3 - "$pr" <<'PY'
import json
import os
import sys

pr = sys.argv[1]
head = os.environ.get("SEAM_HEAD", "sha1")
head_file = os.path.join(os.environ.get("SEAM_HEAD_DIR", ""), pr)
if os.path.isfile(head_file):
    with open(head_file, encoding="utf-8") as handle:
        head = handle.read().strip()
print(json.dumps({
    "headRefOid": head,
    "baseRefName": os.environ.get("SEAM_BASE", "main"),
    "mergeable": os.environ.get("SEAM_FP_MERGEABLE", "MERGEABLE"),
    "mergeStateStatus": os.environ.get("SEAM_FP_MERGE_STATE", "CLEAN"),
    "reviewDecision": os.environ.get("SEAM_RD", "APPROVED"),
    "latestReviews": json.loads(os.environ.get("SEAM_LATEST_REVIEWS", "[]")),
    "labels": [{"name": name} for name in json.loads(os.environ.get("SEAM_LABELS", "[]"))],
    "isDraft": os.environ.get("SEAM_DRAFT", "false") == "true",
    "state": os.environ.get("SEAM_PR_STATE", "OPEN"),
}))
PY
    fi ;;
  fp-checks)
    if [[ -n "${SEAM_FP_CHECKS:-}" ]]; then
      printf '%s\n' "$SEAM_FP_CHECKS"
    else
      python3 - <<'PY'
import json
import os

checks = []
for index, bucket in enumerate(os.environ.get("SEAM_BUCKETS", "pass").split()):
    checks.append({
        "name": f"check-{index}",
        "bucket": bucket,
        "state": "IN_PROGRESS" if bucket == "pending" else "COMPLETED",
        "link": f"https://checks.invalid/{index}",
        "startedAt": "2026-09-19T00:00:00Z",
        "completedAt": None if bucket == "pending" else "2026-09-19T00:01:00Z",
    })
print(json.dumps(checks))
PY
    fi ;;
  fp-threads)
    if [[ -n "${SEAM_FP_THREADS:-}" ]]; then
      printf '%s\n' "$SEAM_FP_THREADS"
    else
      printf '%s\n' '{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[]}}}}}'
    fi ;;
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
  update-branch)    [ "${SEAM_UPDATE_FAIL:-0}" = 1 ] && exit 1 || echo updated ;;
  add-label)
    printf '%s %s\n' "$pr" "${3:-}" >> "${SEAM_LABEL_LOG:?}"
    [ "${SEAM_LABEL_FAIL:-0}" = 1 ] && exit 1 || exit 0 ;;
  do-merge)         [ "${SEAM_MERGE_FAIL:-0}" = 1 ] && exit 1 || echo merged ;;
  headsha)
    if [[ -f "${SEAM_HEAD_DIR:?}/$pr" ]]; then cat "${SEAM_HEAD_DIR}/$pr"; else echo "${SEAM_HEAD:-sha1}"; fi ;;
  basebranch)       echo "${SEAM_BASE:-main}" ;;
  mergecommit)      echo "${SEAM_MERGE_SHA:-mergesha1}" ;;
esac
EOF
    chmod +x "$TMP/seam.sh"
    export PR_MERGE_LOOP_GH_CMD="$TMP/seam.sh"
    export PR_MERGE_LOOP_CLOCK_CMD="$TMP/clock.sh"
    cat > "$TMP/clock.sh" <<'EOF'
#!/usr/bin/env bash
echo "2026-09-19T00:00:00Z"
EOF
    chmod +x "$TMP/clock.sh"

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

    cat > "$TMP/lockseam_degraded.sh" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  has) exit 1 ;;
  add) exit 1 ;;
  remove) exit 0 ;;
esac
EOF
    chmod +x "$TMP/lockseam_degraded.sh"

    # Verification-gate seam. It can fail or change the observed head during
    # dispatch, which exercises the post-dispatch external-transition guard.
    cat > "$TMP/gateseam.sh" <<'EOF'
#!/usr/bin/env bash
printf 'gate\n' >> "${SEAM_GATE_LOG:?}"
if [[ -n "${SEAM_GATE_NEW_HEAD:-}" ]]; then
  printf '%s\n' "$SEAM_GATE_NEW_HEAD" > "${SEAM_HEAD_DIR:?}/${SEAM_GATE_NEW_HEAD_PR:-5}"
fi
[[ "${SEAM_GATE_FAIL:-0}" != 1 ]] || exit 1
_d='{"tier1":{"passed":true},"tier2":{"concerns":[]},"verdict":"APPROVED"}'
echo "${SEAM_GATE:-$_d}"
EOF
    chmod +x "$TMP/gateseam.sh"; export VERIFICATION_GATE_REVIEW_CMD="$TMP/gateseam.sh"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

field() { python3 -c "import json,sys;print(json.load(sys.stdin)[\"$1\"])"; }
action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }
call_count() {
    python3 - "$1" "$SEAM_CALL_LOG" <<'PY'
import sys

op, path = sys.argv[1:3]
with open(path, encoding="utf-8") as handle:
    print(sum(1 for line in handle if line.split(maxsplit=1)[0] == op))
PY
}

gate_count() {
    python3 - "$SEAM_GATE_LOG" <<'PY'
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(sum(1 for line in handle if line.strip()))
PY
}

fingerprint_state() {
    python3 - "$PR_MERGE_LOOP_STATE_DIR" <<'PY'
import glob
import os
import sys

paths = glob.glob(os.path.join(sys.argv[1], "fp_*.json"))
assert len(paths) == 1, paths
print(paths[0])
PY
}

make_race_lock_seam() {
    cat > "$TMP/race-lockseam.sh" <<'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; op="$1"; pr="$2"; owner="${3:-}"; pd="$d/$pr"; mkdir -p "$pd"
case "$op" in
  has)
    newest="" ; shopt -s nullglob
    for f in "$pd"/*; do newest="$(basename "$f")"; done
    [ -n "$newest" ] || exit 1
    printf '0\t%s\n' "$newest" ;;
  add)
    cp "${RACE_STATE:?}" "${RACE_DEST:?}"
    : > "$pd/$owner" ;;
  remove) rm -f "$pd/$owner" ;;
esac
EOF
    chmod +x "$TMP/race-lockseam.sh"
}

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
    # The gate envelopes a Tier-1 fail as reviewer_error (verification_gate.sh's
    # fail-closed shaping), so the transition is degraded — hand-human still
    # surfaces, but non-zero and with no state persisted.
    SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}' run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"hand-human"* ]] && [[ "$output" != *"merged"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
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

# --- material fingerprinting and transition state ---
@test "tick: identical material returns unchanged before reviewer or mutation calls" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"merge"* ]]
    [ "$(gate_count)" = "1" ]

    : > "$SEAM_CALL_LOG"
    : > "$SEAM_LABEL_LOG"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"unchanged"* ]]
    [ "$(gate_count)" = "1" ]
    [ "$(call_count admin-check)" = "0" ]
    [ ! -s "$SEAM_LABEL_LOG" ]
}

@test "fingerprint state is namespaced, strict-schema JSON, atomic, and private" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    state="$(fingerprint_state)"
    python3 - "$state" <<'PY'
import json
import os
import stat
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    state = json.load(handle)
assert set(state) == {"schema_version", "fingerprint", "action", "observed_at"}, state
assert state["schema_version"] == 1
assert len(state["fingerprint"]) == 64
assert state["action"] == "merge"
assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
assert not [name for name in os.listdir(os.path.dirname(path)) if ".tmp." in name]
PY
}

@test "fingerprint state never collides for the same PR number in separate repositories" {
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/one"}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/two"}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    python3 - "$PR_MERGE_LOOP_STATE_DIR" <<'PY'
import glob
import os
import sys

paths = glob.glob(os.path.join(sys.argv[1], "fp_*_5.json"))
assert len(paths) == 2, paths
PY
}

@test "head transition resumes exactly once" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1
    printf 'sha2\n' > "$SEAM_HEAD_DIR/5"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    [ "$(gate_count)" = "2" ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1
    [ "$(gate_count)" = "2" ]
}

@test "a CI rerun that is still pending resumes exactly once" {
    export SEAM_BUCKETS="pending"
    export SEAM_FP_CHECKS='[{"name":"ci","bucket":"pending","state":"IN_PROGRESS","link":"https://checks.invalid/1","startedAt":"2026-09-19T00:00:00Z","completedAt":null}]'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"wait"* ]]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_CHECKS='[{"name":"ci","bucket":"pending","state":"IN_PROGRESS","link":"https://checks.invalid/2","startedAt":"2026-09-19T01:00:00Z","completedAt":null}]'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"wait"* ]] && [[ "$output" != *"unchanged"* ]]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]]
}

@test "a new review with the same decision resumes exactly once" {
    export SEAM_LATEST_REVIEWS='[{"id":"R1","state":"APPROVED","submittedAt":"2026-09-19T00:00:00Z"}]'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_LATEST_REVIEWS='[{"id":"R2","state":"APPROVED","submittedAt":"2026-09-19T01:00:00Z"}]'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    [ "$(gate_count)" = "2" ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]]
}

@test "thread resolution resumes exactly once" {
    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z"}]}}]}}}}}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":true,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z"}]}}]}}}}}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]]
}

@test "array reordering and lease-label churn do not change the fingerprint" {
    export SEAM_LABELS='["zeta","hold","loop-active:1:owner-a"]'
    export SEAM_LATEST_REVIEWS='[{"id":"R2","state":"APPROVED","submittedAt":"2026-09-19T01:00:00Z"},{"id":"R1","state":"COMMENTED","submittedAt":"2026-09-19T00:00:00Z"}]'
    export SEAM_FP_CHECKS='[{"name":"z","bucket":"pass","state":"COMPLETED","link":"z","startedAt":"2","completedAt":"3"},{"name":"a","bucket":"pass","state":"COMPLETED","link":"a","startedAt":"1","completedAt":"2"}]'
    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T2","isResolved":true,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C2","createdAt":"2","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C2","createdAt":"2"}]}},{"id":"T1","isResolved":true,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"1","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"1"}]}}]}}}}}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]

    export SEAM_LABELS='["loop-active:9:owner-b","hold","zeta"]'
    export SEAM_LATEST_REVIEWS='[{"id":"R1","state":"COMMENTED","submittedAt":"2026-09-19T00:00:00Z"},{"id":"R2","state":"APPROVED","submittedAt":"2026-09-19T01:00:00Z"}]'
    export SEAM_FP_CHECKS='[{"name":"a","bucket":"pass","state":"COMPLETED","link":"a","startedAt":"1","completedAt":"2"},{"name":"z","bucket":"pass","state":"COMPLETED","link":"z","startedAt":"2","completedAt":"3"}]'
    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":true,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"1","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"1"}]}},{"id":"T2","isResolved":true,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C2","createdAt":"2","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C2","createdAt":"2"}]}}]}}}}}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"unchanged"* ]]
    [ "$(gate_count)" = "1" ]
}

@test "apply mode, revision budget, and recorded disposition are fingerprint inputs" {
    export SEAM_BUCKETS="pending"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    "$SCRIPT" address-cycle 5 > /dev/null
    PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]

    "$SCRIPT" set-disposition 5 keep
    PR_MERGE_LOOP_APPLY=1 run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
}

@test "failed or malformed observations degrade without overwriting good state" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    state="$(fingerprint_state)"
    before="$(cat "$state")"

    export SEAM_HEAD=sha2 SEAM_FP_FAIL=fp-checks
    run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"observation"* ]]
    [ "$(cat "$state")" = "$before" ]

    unset SEAM_FP_FAIL
    export SEAM_FP_VIEW='not-json'
    run "$SCRIPT" tick 5
    [ "$status" -ne 0 ]
    [ "$(cat "$state")" = "$before" ]
}

@test "corrupt state requires fresh processing and is replaced only after success" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    state="$(fingerprint_state)"
    printf '{\n' > "$state"
    : > "$SEAM_GATE_LOG"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    [ "$(gate_count)" = "1" ]
    python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["schema_version"] == 1' "$state"
}

@test "reviewer infrastructure failure is degraded and never records unchanged state" {
    SEAM_GATE_FAIL=1 run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"review"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
}

@test "failed remote mutation is degraded and never records unchanged state" {
    # On this bundle the only reachable remote mutation is the action label —
    # merge itself is hard-gated before gh_op do-merge. A rejected label write
    # must degrade loudly and leave no transition state.
    PR_MERGE_LOOP_APPLY=1 SEAM_LABEL_FAIL=1 run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"failure"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]
}

@test "fingerprint state write failure is degraded and preserves the conflicting path" {
    printf 'user-owned\n' > "$TMP/not-a-state-directory"
    export PR_MERGE_LOOP_STATE_DIR="$TMP/not-a-state-directory"
    run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"state write failed"* ]]
    [ "$(cat "$PR_MERGE_LOOP_STATE_DIR")" = "user-owned" ]
}

@test "external transition during dispatch leaves state unrecorded for the next tick" {
    export SEAM_GATE_NEW_HEAD=sha2
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"transition"* ]]
    [ ! -e "$PR_MERGE_LOOP_STATE_DIR"/fp_*.json ]

    unset SEAM_GATE_NEW_HEAD
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    [ "$(gate_count)" = "2" ]
    state="$(fingerprint_state)"
    [ -f "$state" ]
}

@test "worker that acquires after another persisted the same material returns unchanged" {
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    state="$(fingerprint_state)"
    cp "$state" "$TMP/raced-state"
    rm "$state"
    export RACE_STATE="$TMP/raced-state" RACE_DEST="$state"
    make_race_lock_seam
    : > "$SEAM_GATE_LOG"
    LOOP_LOCK_LABEL_CMD="$TMP/race-lockseam.sh" run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"unchanged"* ]]
    [ "$(gate_count)" = "0" ]
}

@test "GitHub fingerprint checks accept documented pending and failed statuses only with valid JSON" {
    mkdir -p "$TMP/fake-bin"
    cat > "$TMP/fake-bin/gh" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "pr" && "$2" == "checks" ]] || exit 64
cat "${GH_CHECK_PAYLOAD:?}"
exit "${GH_CHECK_RC:-0}"
EOF
    chmod +x "$TMP/fake-bin/gh"
    printf '%s\n' '[{"name":"ci","bucket":"pending","state":"IN_PROGRESS","link":"","startedAt":"2026-09-19T00:00:00Z","completedAt":null}]' > "$TMP/checks.json"

    script_dir="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin"
    fragment_path="lib/pr_merge_loop_gh.sh"
        for check_rc in 8 1; do
            PATH="$TMP/fake-bin:$PATH" MANIFEST_GIT_PLATFORM=github \
                GH_CHECK_PAYLOAD="$TMP/checks.json" GH_CHECK_RC="$check_rc" \
                run bash -c '
set -euo pipefail
unset PR_MERGE_LOOP_GH_CMD
SCRIPT_DIR="$1"; STATE_DIR="$2"; AUTHORS_FILE=/dev/null
err() { printf "%s\n" "$*" >&2; }
_net() { "$@"; }
source "$SCRIPT_DIR/$3"
gh_op fp-checks 5
' _ "$script_dir" "$TMP/fragment-state" "$fragment_path"
            [ "$status" -eq 0 ]
            echo "$output" | python3 -c 'import json,sys; assert json.load(sys.stdin)[0]["name"] == "ci"'
        done

    printf 'not-json\n' > "$TMP/checks.json"
    PATH="$TMP/fake-bin:$PATH" MANIFEST_GIT_PLATFORM=github \
        GH_CHECK_PAYLOAD="$TMP/checks.json" GH_CHECK_RC=8 \
        run bash -c '
set -euo pipefail
unset PR_MERGE_LOOP_GH_CMD
SCRIPT_DIR="$1"; STATE_DIR="$2"; AUTHORS_FILE=/dev/null
err() { printf "%s\n" "$*" >&2; }
_net() { "$@"; }
source "$SCRIPT_DIR/lib/pr_merge_loop_gh.sh"
gh_op fp-checks 5
' _ "$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin" "$TMP/fragment-state"
    [ "$status" -ne 0 ]
}

@test "unsupported provider fingerprinting is a visible non-success" {
    unset PR_MERGE_LOOP_GH_CMD
    PR_MERGE_LOOP_PLATFORM=gitlab run "$SCRIPT" tick 5
    [ "$status" -ne 0 ] && [[ "$output" == *"unsupported"* ]]
}
@test "gitlab: merge fails closed (no auto-merge parity → ready-to-merge + human)" {
    unset PR_MERGE_LOOP_GH_CMD                # exercise the real platform branch
    PR_MERGE_LOOP_PLATFORM=gitlab run "$SCRIPT" merge 5
    [ "$status" -eq 78 ]
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

@test "run: fully idle pass stops immediately" {
    export SEAM_LIST='[]' PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "1" ]
    [[ "$output" == *"first unchanged pass"* ]]
}

@test "run: changed waiting PR is handled once, then the first unchanged pass stops" {
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]' SEAM_BUCKETS="pending"
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "1" ]
    [ "$(call_count fp-view)" = "4" ]
}

@test "run: one changed PR does not reopen work on unchanged siblings" {
    "$SCRIPT" tick 5 > /dev/null
    "$SCRIPT" tick 6 > /dev/null
    : > "$SEAM_GATE_LOG"
    : > "$SEAM_CALL_LOG"
    printf 'sha2\n' > "$SEAM_HEAD_DIR/5"
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}},{"number":6,"author":{"login":"Copilot","__typename":"Bot"}}]'
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$(gate_count)" = "1" ]
    [ "$(call_count headsha)" = "1" ] # headsha runs only for the fully-processed PR
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

@test "vendored: run handles a transition once and stops on the first idle pass" {
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$VENDORED" run
    [ "$status" -eq 0 ] && [[ "$output" == *"first unchanged pass"* ]]
    [ "$(gate_count)" = "1" ]
    [ "$(call_count fp-view)" = "4" ]
    [ "$("$VENDORED" empty-run get)" = "1" ]
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
