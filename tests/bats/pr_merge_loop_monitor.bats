#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/lib/pr_merge_loop_monitor.sh —
# the provider-degraded run path: unsupported fingerprinting providers exit
# visibly, gitlab merge/signals fail closed, and run degrades to bounded
# queue monitoring (PR #992) with the scope derived from the origin remote.
# Shares the offline seam harness in tests/test_helper/pr_merge_loop_seams.bash
# (split out of pr_merge_loop.bats at the 600-line ceiling — see that file's
# header for the module map).

source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"

setup()    { pr_merge_loop_setup; }
teardown() { pr_merge_loop_teardown; }

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

@test "gitlab: unknown review-thread monitor state fails closed in signals" {
    # PR #953 thread 6: GitLab has no reviewThreads twin, so unresolved-human
    # is unknowable there — it must surface as an observation failure (signals
    # exit 13), never as "0 human threads" that could clear an auto-merge.
    cat > "$TMP/glab" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "ci status") echo ok; exit 0 ;;
  *) echo '{}' ;;
esac
EOF
    chmod +x "$TMP/glab"
    unset PR_MERGE_LOOP_GH_CMD
    PATH="$TMP:$PATH" PR_MERGE_LOOP_PLATFORM=gitlab run "$SCRIPT" signals 5
    [ "$status" -eq 13 ] && [[ "$output" == *"review-thread"* ]]
}

@test "gitlab: run keeps bounded queue monitoring when fingerprinting is unsupported" {
    # PR #992: cmd_run must not die at the fp-scope probe on gitlab — auto-merge
    # is unsupported there (and hard-gated here anyway), but bounded
    # monitoring/listing still applies. A managed MR must reset the empty
    # counter (pending work, never an empty pass) and the loop stays bounded
    # by the ceiling. Runs inside a real git repo with a gitlab origin remote:
    # the monitor derives its counter scope from the remote URL since gh_op
    # fp-scope refuses on gitlab. The now-seam returns 0 twice then huge:
    # pass 1 lists the queue once, the pre-sleep check lands on the deadline.
    cat > "$TMP/glab" <<'EOF'
#!/usr/bin/env bash
if [[ "$1 $2" == "mr list" ]]; then
  printf 'list\n' >> "${SEAM_CALL_LOG:?}"
  echo '[{"iid":5,"author":{"username":"copilot"}}]'
  exit 0
fi
echo '{}'
EOF
    chmod +x "$TMP/glab"
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
c="${TMP:?}/nowc"; n=$(( $( [ -f "$c" ] && cat "$c" || echo 0 ) + 1 )); echo "$n" > "$c"
[ "$n" -le 2 ] && echo 0 || echo 999999
EOF
    chmod +x "$TMP/now.sh"
    unset PR_MERGE_LOOP_GH_CMD
    export PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh" PR_MERGE_LOOP_CEILING_SEC=10 PR_MERGE_LOOP_POLL_SEC=0
    git init -q "$TMP/repo" && cd "$TMP/repo" || return 1
    git remote add origin git@gitlab.com:acme/widgets.git
    # Seed the counter file directly: the `empty-run` CLI fails closed on
    # gitlab (fp-scope refuses), while the monitor maintains the same
    # scope-keyed file via the origin-derived scope.
    count_path="$(gitlab_scope_count_path)"
    mkdir -p "$(dirname "$count_path")"
    printf '2\n' > "$count_path"
    PATH="$TMP:$PATH" PR_MERGE_LOOP_PLATFORM=gitlab run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$(call_count list)" = "1" ]
    # The managed MR counts as pending work: the seeded counter resets, never
    # increments toward the 5-empty stop.
    [ "$(cat "$count_path")" = "0" ]
    [[ "$output" == *"managed queue pending (5)"* ]]
}

@test "gitlab: run's empty queue still stops at the 5-empty threshold" {
    # The degraded monitor path keeps the FR-018a contract: with no managed
    # MRs each pass increments the counter and the loop exits on the counter,
    # not the clock.
    cat > "$TMP/glab" <<'EOF'
#!/usr/bin/env bash
if [[ "$1 $2" == "mr list" ]]; then
  printf 'list\n' >> "${SEAM_CALL_LOG:?}"
  echo '[]'
  exit 0
fi
echo '{}'
EOF
    chmod +x "$TMP/glab"
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
f="${SEAM_NOW_FILE:?}"; n=$(( $(cat "$f" 2>/dev/null || echo 0) + 30 ))
echo "$n" > "$f"; echo "$n"
EOF
    chmod +x "$TMP/now.sh"
    unset PR_MERGE_LOOP_GH_CMD
    export SEAM_NOW_FILE="$TMP/now" PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh"
    export PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    git init -q "$TMP/repo" && cd "$TMP/repo" || return 1
    git remote add origin git@gitlab.com:acme/widgets.git
    PATH="$TMP:$PATH" PR_MERGE_LOOP_PLATFORM=gitlab run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$(cat "$(gitlab_scope_count_path)")" = "5" ]
    [[ "$output" == *"5 consecutive empty passes"* ]]
}
