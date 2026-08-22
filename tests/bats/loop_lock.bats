#!/usr/bin/env bats
# Tests for the VENDORED plugins/manifest-forge/runtime/bin/loop_lock.sh — the
# per-PR concurrency guard shipped in the manifest-forge plugin bundle.
#
# configs/claude/scripts/loop_lock.sh (the operator/bootstrap copy) is a
# separate, unmodified file — out of scope for this task (CDDL QA-critic
# finding, 2026-08-19/20) and not exercised by this file.

SCRIPT="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/loop_lock.sh"

setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/looplock.XXXXXX")
    export LOOP_LOCK_DIR="$TMP/locks"
    export LOOP_LOCK_SETTLE_SEC=0.05 # keep the per-acquire settle window fast in tests
    # Fake label seam. A real GitHub `--add-label` only attaches a label that
    # already exists as a repo label — it never creates one — and labels.yml
    # can never pre-provision the dynamic "loop-active:<epoch>:<owner>" lease
    # name loop_lock.sh requests (the epoch+owner suffix is unbounded,
    # generated fresh per acquisition, so no static registry entry could ever
    # cover it). FIXED (2026-08-20, Finding 1(a)): loop_lock.sh's `label_op
    # add` now self-provisions the label (`gh label create --force`)
    # immediately before attaching it, so a healthy real backend's add
    # succeeds — model that below by recording the lease's epoch, exactly
    # what a real add followed by `has` reading it back would produce.
    # Dedicated tests further down use their own rejecting seam to cover the
    # DEGRADED case (label creation itself still fails — no permission, API
    # error, etc.), which remains realistic even after this fix.
    cat > "$TMP/seam.sh" << 'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; op="$1"; pr="$2"; owner="${3:-}"
pd="$d/$pr"; mkdir -p "$pd"
case "$op" in
  has)
    newest_epoch=""; newest_owner=""
    shopt -s nullglob
    for f in "$pd"/*; do
        epoch="$(cat "$f" 2>/dev/null || echo 0)"
        o="$(basename "$f")"
        if [ -z "$newest_epoch" ] || [ "$epoch" -gt "$newest_epoch" ] || { [ "$epoch" = "$newest_epoch" ] && [[ "$o" > "$newest_owner" ]]; }; then
            newest_epoch="$epoch"; newest_owner="$o"
        fi
    done
    [ -n "$newest_epoch" ] || exit 1
    now=$(date +%s)
    age=$(( (now - newest_epoch) / 60 ))
    [ "$age" -ge 0 ] || age=0
    printf '%s\t%s\n' "$age" "$newest_owner"
    exit 0
    ;;
  add)
    [ -n "$owner" ] || exit 1
    sleep "${SEAM_ADD_DELAY:-0}" # widen the TOCTOU window for the race test below
    date +%s > "$pd/$owner"
    exit 0
    ;;
  remove)
    [ -n "$owner" ] || exit 0
    rm -f "$pd/$owner"
    exit 0
    ;;
esac
EOF
    chmod +x "$TMP/seam.sh"
    export SEAM_STATE="$TMP/labels"
    export LOOP_LOCK_LABEL_CMD="$TMP/seam.sh"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

@test "--help exits 0" { run "$SCRIPT" --help; [ "$status" -eq 0 ]; }
@test "unknown subcommand non-zero" { run "$SCRIPT" bogus 5; [ "$status" -ne 0 ]; }

# --- FIX regression (CDDL QA-critic finding): cmd_acquire used to do
# `label_op add ... || true`, discarding a failed add and reporting the lease
# as taken (exit 0) even though nothing was written. Self-contained: uses its
# own dedicated rejecting seam, independent of the suite-wide one above, so
# this regression stands on its own regardless of how that fixture evolves. ---
@test "FIX: a rejecting label backend fails the acquire, not succeeds" {
    cat > "$TMP/reject-seam.sh" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  has) exit 1 ;;   # no existing lease on record
  add) exit 1 ;;   # backend rejects the add (e.g. label not pre-provisioned)
  remove) exit 0 ;;
esac
EOF
    chmod +x "$TMP/reject-seam.sh"
    LOOP_LOCK_LABEL_CMD="$TMP/reject-seam.sh" run "$SCRIPT" acquire 55
    [ "$status" -ne 0 ]                  # must fail, never silently succeed
    [ ! -f "$LOOP_LOCK_DIR/55.owner" ]   # and no lease state for a lock never actually taken
    LOOP_LOCK_LABEL_CMD="$TMP/reject-seam.sh" run "$SCRIPT" is-held 55
    [ "$status" -ne 0 ]                  # is-held agrees: not held
}

# --- PROPORTIONALITY FIX (2026-08-20): fail-closed must not collapse two
# different conditions into the same signal. A backend that can't even attempt
# the lease (add rejected) is DEGRADED, not evidence that anyone holds it; a
# live lease actually on record for someone else is genuine CONTENTION. A
# caller (pr_merge_loop.sh's cmd_tick) needs to tell these apart to decide
# whether to proceed without the cross-host lock or to block. ---
@test "FIX: a rejected add returns the DEGRADED code (2), distinct from the CONTENDED code (1)" {
    cat > "$TMP/reject-seam.sh" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  has) exit 1 ;;   # no existing lease on record — nobody holds it
  add) exit 1 ;;   # backend rejects the add (e.g. label not pre-provisioned)
  remove) exit 0 ;;
esac
EOF
    chmod +x "$TMP/reject-seam.sh"
    LOOP_LOCK_LABEL_CMD="$TMP/reject-seam.sh" run "$SCRIPT" acquire 55
    [ "$status" -eq 2 ] # DEGRADED, not the "held" code — no one is proven to hold anything
}
@test "FIX: a genuinely held (live, non-stale) lease still returns the CONTENDED code (1)" {
    cat > "$TMP/held-seam.sh" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  has) printf '0\tother-owner\n'; exit 0 ;;  # fresh lease already on record, owned by someone else
  add) exit 1 ;;   # never reached — held_active blocks before any add is attempted
  remove) exit 0 ;;
esac
EOF
    chmod +x "$TMP/held-seam.sh"
    LOOP_LOCK_LABEL_CMD="$TMP/held-seam.sh" run "$SCRIPT" acquire 66
    [ "$status" -eq 1 ] # CONTENDED — a real lease is on record, distinct from the degraded case above
}

# --- Everything below exercises the suite-wide seam from setup(), which now
# (Finding 1(a)) models a HEALTHY backend: `label_op add` self-provisions the
# dynamic lease label before attaching it, so a real add succeeds and
# `acquire` can actually take the platform lease — matching production once
# the fix ships. Tests below that previously asserted "acquire succeeds" (and
# were skipped when the seam was made faithful to the UNFIXED backend) are
# reinstated. Dedicated DEGRADED-path coverage (backend still can't attempt
# the add — e.g. no label-create permission) lives in the "FIX:" tests above,
# which use their own rejecting seam independent of this one. ---

@test "acquire on a free PR succeeds" {
    run "$SCRIPT" acquire 42
    [ "$status" -eq 0 ]
}
@test "is-held reflects state after acquire" {
    "$SCRIPT" acquire 42
    run "$SCRIPT" is-held 42
    [ "$status" -eq 0 ]
}
@test "second acquire on a held PR fails (exit 1)" {
    "$SCRIPT" acquire 42
    run "$SCRIPT" acquire 42
    [ "$status" -eq 1 ]
}
@test "release frees the lock; re-acquire succeeds" {
    "$SCRIPT" acquire 42
    run "$SCRIPT" release 42; [ "$status" -eq 0 ]
    run "$SCRIPT" is-held 42; [ "$status" -ne 0 ]
    run "$SCRIPT" acquire 42; [ "$status" -eq 0 ]
}
@test "release is idempotent (releasing an unheld PR is ok)" {
    run "$SCRIPT" release 99
    [ "$status" -eq 0 ]
}
@test "stale lock (age > LOOP_LOCK_STALE_MIN) is reclaimable" {
    mkdir -p "$SEAM_STATE/42"
    echo "$(($(date +%s) - 99 * 60))" > "$SEAM_STATE/42/stale-owner" # 99-min-old lease
    LOOP_LOCK_STALE_MIN=15 run "$SCRIPT" acquire 42
    [ "$status" -eq 0 ] # reclaimed, not blocked
}

# --- finding 4 regression: two runners racing the same PR must never both win ---
@test "race: two concurrent acquires on the same PR — exactly one wins" {
    # Widen the TOCTOU window inside the fake platform so both runners are
    # genuinely in-flight at once, not accidentally serialized by disk I/O,
    # and give the settle window enough margin to observe both writes.
    export SEAM_ADD_DELAY=0.3 LOOP_LOCK_SETTLE_SEC=0.5
    LOOP_LOCK_STALE_MIN=15 "$SCRIPT" acquire 77 > "$TMP/out_a.log" 2>&1 &
    a_pid=$!
    LOOP_LOCK_STALE_MIN=15 "$SCRIPT" acquire 77 > "$TMP/out_b.log" 2>&1 &
    b_pid=$!
    a_rc=0; wait "$a_pid" || a_rc=$?
    b_rc=0; wait "$b_pid" || b_rc=$?

    wins=0
    [ "$a_rc" -eq 0 ] && wins=$((wins + 1))
    [ "$b_rc" -eq 0 ] && wins=$((wins + 1))
    [ "$wins" -eq 1 ] # never both, never neither
}

# --- fail-closed on an UNREADABLE lease (Codex P1, 2026-08-22) --------------
# `label_op has` used to return 1 both when the read succeeded with no lease
# AND when the lookup itself failed, so a transient API error read as "free"
# and two runners could acquire concurrently -- in the operator copy that
# leads into a real `gh pr merge --admin`. 2 now means "could not read".

@test "acquire: unreadable lease state fails CLOSED (exit 2), never acquires" {
    cat > "$TMP/unreadable-seam.sh" << 'EOF'
#!/usr/bin/env bash
[ "$1" = has ] && exit 2   # lookup itself failed
exit 0
EOF
    chmod +x "$TMP/unreadable-seam.sh"
    LOOP_LOCK_LABEL_CMD="$TMP/unreadable-seam.sh" run "$SCRIPT" acquire 71
    [ "$status" -eq 2 ]
    [[ "$output" == *"unreadable"* ]]
}

@test "acquire: a clean 'no lease' read (exit 1) still acquires normally" {
    # Regression guard for the fix above: only status 2 may fail closed. If
    # this ever fails, the fail-closed branch has swallowed the happy path.
    run "$SCRIPT" acquire 72
    [ "$status" -eq 0 ]
}

# --- holds / renew (Codex P1 #8: a long tick must not outlive its lease) ----

@test "holds: true while we own a live lease, false after release" {
    run "$SCRIPT" acquire 73
    [ "$status" -eq 0 ]
    run "$SCRIPT" holds 73
    [ "$status" -eq 0 ]
    run "$SCRIPT" release 73
    run "$SCRIPT" holds 73
    [ "$status" -ne 0 ]
}

@test "holds: false when someone else owns the lease" {
    run "$SCRIPT" acquire 74
    [ "$status" -eq 0 ]
    rm -f "$LOOP_LOCK_DIR/74.owner"          # we no longer know the owner
    printf 'someone-else' > "$LOOP_LOCK_DIR/74.owner"
    run "$SCRIPT" holds 74
    [ "$status" -ne 0 ]
}

@test "renew: refreshes our lease and we still hold it afterwards" {
    run "$SCRIPT" acquire 75
    [ "$status" -eq 0 ]
    run "$SCRIPT" renew 75
    [ "$status" -eq 0 ]
    run "$SCRIPT" holds 75
    [ "$status" -eq 0 ]
}

@test "renew: DEGRADED (exit 2) when the backend rejects the refresh add" {
    run "$SCRIPT" acquire 76
    [ "$status" -eq 0 ]
    cat > "$TMP/reject-add-seam.sh" << 'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; op="$1"; pr="$2"
case "$op" in
  add) exit 1 ;;
  has) pd="$d/$pr"; shopt -s nullglob; for f in "$pd"/*; do
         printf '0\t%s\n' "$(basename "$f")"; exit 0; done; exit 1 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$TMP/reject-add-seam.sh"
    LOOP_LOCK_LABEL_CMD="$TMP/reject-add-seam.sh" run "$SCRIPT" renew 76
    [ "$status" -eq 2 ]
}

@test "renew: fails when we never held the lease" {
    run "$SCRIPT" renew 77
    [ "$status" -eq 1 ]
}
