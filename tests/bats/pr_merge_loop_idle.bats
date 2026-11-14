#!/usr/bin/env bats
# Human-idle disposition uses the real persisted fingerprint/driver boundary.
source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"

setup() { pr_merge_loop_setup; }
teardown() { pr_merge_loop_teardown; }

@test "human-blocked second invocation is one line and zero reviewer calls" {
    export SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    [ "$(gate_count)" = "1" ]
    run "$SCRIPT" address-status 5
    [ "$status" -eq 0 ]
    [ "$output" = "blocked on human: #5" ]
    [ "$(gate_count)" = "1" ]
    run "$SCRIPT" address-status 5
    [ "$output" = "blocked on human: #5" ]
    [ "$(gate_count)" = "1" ]
    python3 - "$(fingerprint_state)" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]))
assert state['observed_at']=='2026-09-19T00:00:00Z'
assert state['action']=='hand-human'
PY
}

@test "run consumes human-idle disposition without another polling pass" {
    export SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}'
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    : > "$SEAM_CALL_LOG"
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$output" = $'blocked on human: #5\nloop idle: waiting on human' ]
    [ "$(call_count list)" = "1" ]
    [ "$(gate_count)" = "1" ]
}

@test "new actionable feedback reenters after human idle without resolving threads" {
    export SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    export SEAM_LATEST_REVIEWS='[{"author":{"login":"human"},"state":"CHANGES_REQUESTED","submittedAt":"2026-09-20T00:00:00Z","body":"new concern"}]'
    run "$SCRIPT" address-status 5
    [ "$status" -eq 0 ]
    [ "$output" = "actionable: #5" ]
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    [ "$(gate_count)" = "2" ]
    [ "$(call_count resolve-thread)" = "0" ]
}

@test "discussion comment and edits reopen human-idle material" {
    export SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    export SEAM_ISSUE_COMMENTS='[[{"id":99,"body":"new concern","updated_at":"2026-09-20T00:00:00Z"}]]'
    run "$SCRIPT" address-status 5
    [ "$output" = "actionable: #5" ]
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    [ "$(gate_count)" = "2" ]
    run "$SCRIPT" address-status 5
    [ "$output" = "blocked on human: #5" ]
    export SEAM_ISSUE_COMMENTS='[[{"id":99,"body":"edited concern","updated_at":"2026-09-20T00:00:00Z"}]]'
    run "$SCRIPT" address-status 5
    [ "$output" = "actionable: #5" ]
    [ "$(gate_count)" = "2" ]
}

@test "review-thread body edit reopens even with unchanged comment identity and creation time" {
    export SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}'
    export SEAM_FP_THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"T1","isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z","body":"concern","author":{"login":"human"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z","body":"concern"}]}}]}}}}}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" address-status 5
    [ "$output" = "blocked on human: #5" ]
    export SEAM_FP_THREADS="${SEAM_FP_THREADS//concern/edited}"
    run "$SCRIPT" address-status 5
    [ "$output" = "actionable: #5" ]
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    [ "$(gate_count)" = "2" ]
    [ "$(call_count resolve-thread)" = "0" ]
}

@test "failed feedback observation is unverified and never certifies idle" {
    export SEAM_GATE='{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED"}'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    export SEAM_FP_FAIL=feedback
    run "$SCRIPT" address-status 5
    [ "$status" -eq 13 ]
    [[ "$output" != *"blocked on human"* ]] || return 1
    [ "$(gate_count)" = "1" ]
}

@test "skill records an observed human block locally and refuses a stale disposition" {
    run "$SCRIPT" address-status 5 --json
    [ "$status" -eq 0 ]
    observed="$(printf '%s' "$output" | field fingerprint)"
    run "$SCRIPT" record-human-blocked 5 "$observed"
    [ "$status" -eq 0 ]
    [ "$output" = "blocked on human: #5" ]
    run "$SCRIPT" address-status 5
    [ "$output" = "blocked on human: #5" ]
    [ "$(gate_count)" = "0" ]
    export SEAM_INLINE_COMMENTS='[[{"id":99,"body":"edited older inline feedback outside the GraphQL page","updated_at":"2026-09-20T00:00:00Z"}]]'
    run "$SCRIPT" record-human-blocked 5 "$observed"
    [ "$status" -eq 13 ]
    run "$SCRIPT" address-status 5
    [ "$output" = "actionable: #5" ]
    [ "$(gate_count)" = "0" ]
    [ "$(call_count resolve-thread)" = "0" ]
}
