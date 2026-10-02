#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/lib/pr_merge_loop_empty_run.sh —
# the per-scope consecutive-empty counter (get/incr/reset, repo-scoped files,
# flock serialization) — and the cmd_run driver: hard ceiling, 5-empty stop,
# in-flight work resetting the counter (FR-018a), post-lease material re-read.
# Shares the offline seam harness in tests/test_helper/pr_merge_loop_seams.bash
# (split out of pr_merge_loop.bats at the 600-line ceiling — see that file's
# header for the module map).

source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"

setup()    { pr_merge_loop_setup; }
teardown() { pr_merge_loop_teardown; }

# --- empty-run counter ---
@test "empty-run get/incr/reset" {
    run "$SCRIPT" empty-run get;   [ "$output" = "0" ]
    run "$SCRIPT" empty-run incr;  [ "$output" = "1" ]
    run "$SCRIPT" empty-run incr;  [ "$output" = "2" ]
    run "$SCRIPT" empty-run reset; [ "$output" = "0" ]
    run "$SCRIPT" empty-run get;   [ "$output" = "0" ]
}

@test "empty-run counter is scoped per repository" {
    # STATE_DIR is shared across repositories (XDG default), so the counter
    # file must be keyed on the repository scope — acme/one's empty passes must
    # never advance acme/two's counter, and two scopes sharing one state dir
    # must keep independent counts.
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/one"}'
    run "$SCRIPT" empty-run incr; [ "$output" = "1" ]
    run "$SCRIPT" empty-run incr; [ "$output" = "2" ]
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/two"}'
    run "$SCRIPT" empty-run get;  [ "$output" = "0" ]
    run "$SCRIPT" empty-run incr; [ "$output" = "1" ]
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/one"}'
    run "$SCRIPT" empty-run get;  [ "$output" = "2" ]
    run "$SCRIPT" empty-run reset; [ "$output" = "0" ]
}

@test "empty-run serializes concurrent incr/reset under an exclusive lock" {
    # Read-modify-write runs under fcntl.flock on the counter file, so N
    # concurrent incr processes lose no updates and a reset cannot interleave
    # between another process's read and write. 60 parallel incr must yield
    # exactly 60 (a bare cat/echo counter drops increments under load).
    export SEAM_SCOPE='{"host":"github.com","owner_repo":"acme/widgets"}'
    for _ in $(seq 60); do "$SCRIPT" empty-run incr > /dev/null & done
    wait
    run "$SCRIPT" empty-run get; [ "$output" = "60" ]
    "$SCRIPT" empty-run reset > /dev/null &
    wait
    run "$SCRIPT" empty-run get; [ "$output" = "0" ]
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

@test "run: fully idle passes stop at the documented 5-empty threshold" {
    # now-seam: +30s per _now call. Each pass costs 3 calls (top, post-loop,
    # pre-sleep); five empty passes land at now=480 < deadline — the loop exits
    # via the counter, not the clock.
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 30 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export SEAM_LIST='[]' PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "5" ]
    [[ "$output" == *"5 consecutive empty passes"* ]]
}

@test "run: a preserved empty_count keeps incrementing across empty passes" {
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 30 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export SEAM_LIST='[]' PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    # 2 preserved + 3 fresh empty passes -> 5, then stop.
    [ "$("$SCRIPT" empty-run get)" = "5" ]
    [[ "$output" == *"5 consecutive empty passes"* ]]
}

@test "run: an unchanged PR whose recorded action is still pending stays in flight" {
    # FR-018a regression: a PR whose fingerprint matches but whose recorded
    # action is `wait` (checks still settling) is in-flight work — the empty
    # counter must RESET, never increment, so the loop keeps polling instead of
    # walking to the 5-empty stop. Seeded counter 2 -> 0 proves the reset ran.
    export SEAM_BUCKETS="pending"
    "$SCRIPT" tick 5 > /dev/null 2>&1   # persists fingerprint with action=wait
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 100 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "0" ]
}

@test "run: racing worker's in-flight verdict is read from post-lease material" {
    # Regression for PR #992 review thread PRRT_kwDOPe2ygc6mVlHk: cmd_run's
    # pre-lease material is STALE when cmd_tick's `unchanged` verdict rested on
    # its post-lease re-read (the racing worker persisted state for the NEW
    # material mid-tick). Classifying under the stale fingerprint finds no
    # recorded action, so a still-pending `wait` verdict looks settled and the
    # empty counter advances toward the 5-empty stop instead of resetting.
    # The fix re-observes material before the in-flight lookup.
    export SEAM_BUCKETS="pending"
    printf 'sha2\n' > "$SEAM_HEAD_DIR/5"
    "$SCRIPT" tick 5 > /dev/null 2>&1   # persists fingerprint for sha2 with action=wait
    state="$(fingerprint_state)"
    cp "$state" "$TMP/raced-state"
    # The racing worker persisted state for the sha2 material; cmd_run's
    # per-PR observation happens first and must still see the OLD material, so
    # the head reverts to sha1 until the lease-add seam flips it back to sha2.
    rm "$state" "$SEAM_HEAD_DIR/5"
    export RACE_STATE="$TMP/raced-state" RACE_DEST="$state" RACE_HEAD=sha2
    make_race_lock_seam
    : > "$SEAM_GATE_LOG"
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 100 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    LOOP_LOCK_LABEL_CMD="$TMP/race-lockseam.sh" run "$SCRIPT" run
    [ "$status" -eq 0 ]
    # sha2 material matches the raced-in `wait` state: the pass is in-flight, so
    # the seeded counter resets to 0 — under the stale sha1 material it would
    # have incremented to 3. No second pass races: the deadline lands on pass
    # 2's per-PR clock check.
    [ "$("$SCRIPT" empty-run get)" = "0" ]
    [ "$(gate_count)" = "0" ]
}

@test "run: a waiting PR keeps the loop polling — the empty counter never starts" {
    # pending checks -> action `wait`, which is in-flight work (FR-018a): each
    # pass resets the counter rather than incrementing it, so the loop only
    # exits on the deadline. now-seam +100s/call: pass 1 completes below the
    # ceiling, pass 2's per-PR check lands on the deadline -> break.
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 100 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]' SEAM_BUCKETS="pending"
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "0" ]
    [ "$(call_count fp-view)" = "3" ]
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

@test "run: material that changed after an unchanged verdict counts as active" {
    # Regression for PR #992 review thread PRRT_kwDOPe2ygc6oW0ho: cmd_tick may
    # return `unchanged` for material A, yet the PR changes to B before
    # cmd_run's post-tick re-observation. The recorded-action lookup for B is
    # then empty — if that silence counts as settled, the pass is empty and a
    # seeded counter reaches 5, stopping the loop with B still unhandled.
    # The pass must count as active work (counter resets to 0) instead.
    "$SCRIPT" tick 5 > /dev/null 2>&1   # persists fingerprint + action for sha1
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    "$SCRIPT" empty-run incr > /dev/null
    # fp-view serves sha1 on the first observation per run, sha2 on every
    # later call: the tick matches sha1, the re-observation lands on sha2.
    cat > "$TMP/shift-seam.sh" <<'EOF'
#!/usr/bin/env bash
c="${TMP:?}/view-count"
if [[ "$1" == "fp-view" ]]; then
    n=$(( $(cat "$c" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$c"
    ((n < 2)) || printf 'sha2\n' > "${SEAM_HEAD_DIR:?}/$2"
fi
exec "$SEAM_INNER" "$@"
EOF
    chmod +x "$TMP/shift-seam.sh"
    export SEAM_INNER="$TMP/seam.sh" PR_MERGE_LOOP_GH_CMD="$TMP/shift-seam.sh"
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 100 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    # The sha2 material is unrecorded work, so the pass is active and the
    # seeded counter resets to 0; the buggy build increments it to 5 and stops.
    [ "$("$SCRIPT" empty-run get)" = "0" ]
    [[ "$output" != *"5 consecutive empty passes"* ]]
}
