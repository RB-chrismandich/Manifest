#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/lib/pr_merge_loop_fp.sh — the
# material fingerprinting layer: namespaced strict-schema state, resume-once
# semantics across head/CI/review/thread transitions, fingerprint inputs and
# stability, degraded-path never-record rules, and the post-lease race recheck.
# Shares the offline seam harness in tests/test_helper/pr_merge_loop_seams.bash
# (split out of pr_merge_loop.bats at the 600-line ceiling — see that file's
# header for the module map).

source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"

setup()    { pr_merge_loop_setup; }
teardown() { pr_merge_loop_teardown; }

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
@test "gh review material with an empty id fingerprints on author/submittedAt/state/body" {
    # Regression for PR #953 review thread PRRT_kwDOPe2ygc6kRbeA: gh 2.100
    # emits "id":"" inside latestReviews, so fingerprinting must never require
    # it — otherwise every reviewed PR exits 13 during material observation.
    export SEAM_LATEST_REVIEWS='[{"id":"","author":{"login":"Copilot"},"state":"APPROVED","submittedAt":"2026-09-19T00:00:00Z","body":"lgtm"}]'
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" == *"merge"* ]]
    [ "$(gate_count)" = "1" ]

    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1
    [ "$(gate_count)" = "1" ]

    export SEAM_LATEST_REVIEWS='[{"id":"","author":{"login":"Copilot"},"state":"COMMENTED","submittedAt":"2026-09-19T01:00:00Z","body":"nudge"}]'
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
@test "deleting an older human comment resumes the loop even when latestComments is unchanged" {
    # PR #953 thread 17: count_unresolved_human reads every comment's author;
    # a human objection followed by a bot reply leaves latestComments identical
    # before and after the human comment is deleted, so the fingerprint must
    # cover full comment material or the PR stays stuck on `unchanged`.
    local base='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":false},"nodes":__COMMENTS__},"latestComments":{"nodes":[{"id":"C2","createdAt":"2026-09-19T01:00:00Z"}]}}]}}}}}'
    local human_then_bot='[{"id":"C1","createdAt":"2026-09-19T00:00:00Z","author":{"login":"some-human"}},{"id":"C2","createdAt":"2026-09-19T01:00:00Z","author":{"login":"Copilot"}}]'
    local bot_only='[{"id":"C2","createdAt":"2026-09-19T01:00:00Z","author":{"login":"Copilot"}}]'

    export SEAM_FP_THREADS="${base/__COMMENTS__/$human_then_bot}"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_THREADS="${base/__COMMENTS__/$bot_only}"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]]
}

@test "comment pagination truncation flips the fingerprint" {
    # Same thread 17: hasNextPage on the comments connection is part of the
    # blocking classification (truncated = treat as blocking), so toggling it
    # with identical visible comments must still resume the loop.
    local base='{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"id":"T1","isResolved":false,"isOutdated":false,"comments":{"pageInfo":{"hasNextPage":__TRUNC__},"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z","author":{"login":"Copilot"}}]},"latestComments":{"nodes":[{"id":"C1","createdAt":"2026-09-19T00:00:00Z"}]}}]}}}}}'
    export SEAM_FP_THREADS="${base/__TRUNC__/true}"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ]
    run "$SCRIPT" tick 5
    [[ "$output" == *"unchanged"* ]] || return 1

    export SEAM_FP_THREADS="${base/__TRUNC__/false}"
    run "$SCRIPT" tick 5
    [ "$status" -eq 0 ] && [[ "$output" != *"unchanged"* ]]
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
