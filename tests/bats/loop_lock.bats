#!/usr/bin/env bats
# Tests for configs/claude/scripts/loop_lock.sh — per-PR concurrency guard.

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/loop_lock.sh"

setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/looplock.XXXXXX")
    export LOOP_LOCK_DIR="$TMP/locks"
    # Fake label seam backed by files in $TMP/labels (persists across invocations).
    # Protocol: <cmd> has|add|remove <pr>; `has` prints age-minutes, exit 0 if held.
    cat > "$TMP/seam.sh" <<'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; mkdir -p "$d"; op="$1"; pr="$2"; f="$d/$pr"
case "$op" in
  has)    [ -f "$f" ] && { cat "$f"; exit 0; } || exit 1 ;;
  add)    echo "${SEAM_AGE:-0}" > "$f"; exit 0 ;;
  remove) rm -f "$f"; exit 0 ;;
esac
EOF
    chmod +x "$TMP/seam.sh"
    export SEAM_STATE="$TMP/labels"
    export LOOP_LOCK_LABEL_CMD="$TMP/seam.sh"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

@test "--help exits 0" { run "$SCRIPT" --help; [ "$status" -eq 0 ]; }
@test "unknown subcommand non-zero" { run "$SCRIPT" bogus 5; [ "$status" -ne 0 ]; }

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
    mkdir -p "$SEAM_STATE"; echo "99" > "$SEAM_STATE/42"   # pre-existing 99-min-old lock
    LOOP_LOCK_STALE_MIN=15 run "$SCRIPT" acquire 42
    [ "$status" -eq 0 ]                                     # reclaimed, not blocked
}
