#!/usr/bin/env bats
# Tests for configs/claude/scripts/issue_support.sh
# Engine guarantees: resolution precedence, fail-open, idempotency, forward-only
# transitions, closed/locked skip, enabled gate, create-flow, background fallback.

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/issue_support.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/issue_support.XXXXXX")
    export FIXTURE_DIR="$TMP/fixtures"
    mkdir -p "$FIXTURE_DIR"

    # Temp git repo with a numbered branch + one commit (for current_branch / git log)
    REPO="$TMP/repo"
    git init -q "$REPO"
    cd "$REPO" || return 1
    git config user.email t@t.t; git config user.name t
    git checkout -q -b 017-test-branch
    git commit -q --allow-empty -m "work"

    # Stub git_platform.sh → github
    cat >"$TMP/git_platform.sh" <<'EOF'
#!/usr/bin/env bash
echo "${STUB_PLATFORM:-github}"
EOF
    chmod +x "$TMP/git_platform.sh"

    # Stub git_ops.sh: log calls, emit fixtures, honor *_RC env for exit codes
    cat >"$TMP/git_ops.sh" <<'EOF'
#!/usr/bin/env bash
sub="$1"; shift
echo "$sub $*" >> "${CALL_LOG:-/dev/null}"
case "$sub" in
  issue-view)
    n="$1"
    if [[ -f "${FIXTURE_DIR}/issue-${n}.json" ]]; then cat "${FIXTURE_DIR}/issue-${n}.json"; fi
    ;;
  pr-view)   [[ -f "${FIXTURE_DIR}/pr.json" ]] && cat "${FIXTURE_DIR}/pr.json" || true ;;
  issue-list) printf '%s' "${ISSUE_LIST_OUT:-}" ;;
  issue-edit) exit "${EDIT_RC:-0}" ;;
  issue-comment) exit "${COMMENT_RC:-0}" ;;
  issue-create) exit "${CREATE_RC:-0}" ;;
  pr-edit) exit "${PREDIT_RC:-0}" ;;
  *) exit "${GITOPS_RC:-0}" ;;
esac
exit "${GITOPS_RC:-0}"
EOF
    chmod +x "$TMP/git_ops.sh"

    # Stub tracker_ops.sh: records calls to CALL_LOG (same log as git_ops.sh,
    # matching the file's shared stubbing convention). resolve-provider honors
    # STUB_PLATFORM (same knob the git_platform.sh stub used pre-Task-7).
    # issue-transition/issue-comment honor EDIT_RC/COMMENT_RC for ordinary
    # failures, and TRACKER_RC to simulate the tracker_ops provider-limitation
    # exit codes (3 = MCP-only provider, 4 = verb not implemented) — mirroring
    # tracker_ops.sh's own "unsupported-in-context" / "not implemented" wording
    # on stderr so callers can assert the fail-open reason was logged.
    # NOTE: on success, issue-transition/issue-comment echo a fake gh/glab-style
    # issue URL to stdout — mirroring real `gh issue edit`/`gh issue comment`,
    # which print the issue URL on SUCCESS too (Task 7 finding: this must never
    # leak into issue_support.sh's own output). On a genuine (non-3/4) failure
    # they emit a diagnostic on stderr, which the caller IS expected to surface.
    cat >"$TMP/tracker_ops.sh" <<'EOF'
#!/usr/bin/env bash
sub="$1"; shift
echo "$sub $*" >> "${CALL_LOG:-/dev/null}"
case "$sub" in
  resolve-provider) echo "${STUB_PLATFORM:-github}"; exit 0 ;;
  issue-transition)
    if [[ -n "${TRACKER_RC:-}" ]]; then
      echo "tracker-ops: unsupported-in-context: simulated provider limitation" >&2
      exit "${TRACKER_RC}"
    fi
    if [[ "${EDIT_RC:-0}" -ne 0 ]]; then
      echo "tracker-ops: issue-transition failed: simulated genuine error" >&2
      exit "${EDIT_RC}"
    fi
    echo "https://github.com/example/repo/issues/${1:-0}"
    exit 0
    ;;
  issue-comment)
    if [[ -n "${TRACKER_RC:-}" ]]; then
      echo "tracker-ops: unsupported-in-context: simulated provider limitation" >&2
      exit "${TRACKER_RC}"
    fi
    if [[ "${COMMENT_RC:-0}" -ne 0 ]]; then
      echo "tracker-ops: issue-comment failed: simulated genuine error" >&2
      exit "${COMMENT_RC}"
    fi
    echo "https://github.com/example/repo/issues/${1:-0}#issuecomment-1"
    exit 0
    ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$TMP/tracker_ops.sh"

    export GIT_PLATFORM_BIN="$TMP/git_platform.sh"
    export GIT_OPS_BIN="$TMP/git_ops.sh"
    export TRACKER_OPS_BIN="$TMP/tracker_ops.sh"
    export CALL_LOG="$TMP/calls.log"

    # Config with both skills enabled
    export ISSUE_SUPPORT_CONFIG="$TMP/config.yml"
    cat >"$ISSUE_SUPPORT_CONFIG" <<'EOF'
tool_policies:
  issue-sync-pr:
    enabled: true
    hook_timeout_seconds: 5
  issue-sync-commit:
    enabled: true
    hook_timeout_seconds: 5
    commit_hook_mode: sync
EOF
}

teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

mk_issue() { # mk_issue <n> <state> <label>
    cat >"$FIXTURE_DIR/issue-$1.json" <<EOF
{"number":$1,"state":"$2","labels":[$( [[ -n "$3" ]] && printf '{"name":"%s"}' "$3" )],"title":"t"}
EOF
}

# --- resolution -------------------------------------------------------------

@test "resolve: branch prefix yields issue number" {
    run "$SCRIPT" resolve --branch 017-test-branch
    [ "$status" -eq 0 ]
    [[ "$output" == *"17"* ]]
}

@test "resolve: no association returns code 3" {
    run "$SCRIPT" resolve --branch hotfix-no-number
    [ "$status" -eq 3 ]
}

@test "resolve --json emits full IssueRef (number, source, exists, state, label)" {
    mk_issue 17 open planned
    run "$SCRIPT" resolve --branch 017-test-branch --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":17'* ]] || return 1
    [[ "$output" == *'"source":"branch-prefix"'* ]] || return 1
    [[ "$output" == *'"exists":true'* ]] || return 1
    [[ "$output" == *'"state":"open"'* ]] || return 1
    [[ "$output" == *'"label":"planned"'* ]]
}

@test "resolve --json marks a non-existent candidate exists:false" {
    # no fixture for #17 → issue_record returns empty
    run "$SCRIPT" resolve --branch 017-test-branch --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"exists":false'* ]]
}

# --- fail-open (C1) ---------------------------------------------------------

@test "sync-pr exits 0 even when tracker calls fail (fail-open)" {
    mk_issue 17 open planned
    GITOPS_RC=1 EDIT_RC=1 COMMENT_RC=1 run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
}

@test "sync-commit exits 0 when platform is plain git (no-op)" {
    STUB_PLATFORM=git run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
}

# --- enabled gate (FR-015) --------------------------------------------------

@test "sync-pr is a no-op when disabled" {
    cat >"$ISSUE_SUPPORT_CONFIG" <<'EOF'
tool_policies:
  issue-sync-pr:
    enabled: false
EOF
    run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
    [[ "$output" == *"disabled"* ]]
}

# --- forward-only / idempotent (C2, C5) -------------------------------------

@test "sync-pr is a no-op when issue already at needs-review" {
    mk_issue 17 open needs-review
    run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
    [[ "$output" == *"transition"*"skipped"* ]]
}

# --- closed/locked skip (C4) ------------------------------------------------

@test "sync-pr skips a closed issue" {
    mk_issue 17 closed planned
    run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
    [[ "$output" == *"#17"*"skipped"*"closed"* ]]
}

# --- ref strength: bare mentions never close or advance (sync-pr greedy-ref fix) ---

@test "sync-pr: bare #N body mention gets back-link only — no transition, no Closes" {
    # PR body mentions #99 without a closing verb (e.g. "Tracking epic: #99").
    printf 'This slice is part of epic #99.' >"$FIXTURE_DIR/pr.json"
    mk_issue 17 open planned
    mk_issue 99 open ""
    run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
    # NOTE: `|| return 1` on every non-final [[ ]]: under macOS bash 3.2, a failing [[ ]]
    # mid-test is swallowed by errexit and the test silently passes.
    [[ "$output" == *"#99 comment back-link"* ]] || return 1
    [[ "$output" != *"closing-keyword Closes #99"* ]] || return 1
    [[ "$output" != *"#99 transition"* ]] || return 1
    # the branch-prefix issue (#17) still gets the full treatment
    [[ "$output" == *"closing-keyword Closes #17"* ]]
}

@test "sync-pr: explicit 'Closes #N' body ref gets the full treatment" {
    printf 'Fixes the thing.\n\nCloses #88' >"$FIXTURE_DIR/pr.json"
    mk_issue 17 open planned
    mk_issue 88 open planned
    run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
    [[ "$output" == *"#88 transition"* ]] || return 1
    [[ "$output" == *"closing-keyword Closes #88 [skipped] (already present)"* ]]
}

# --- commit: only advances planned (FR-006) ---------------------------------

@test "sync-commit skips an unlabeled issue" {
    mk_issue 17 open ""
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"unlabeled"* ]]
}

@test "sync-commit transitions a planned issue toward in-progress" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"#17 transition planned→in-progress"* ]]
}

# --- background fallback (FR-016) -------------------------------------------

@test "commit_hook_mode=background falls back to sync with a warning" {
    cat >"$ISSUE_SUPPORT_CONFIG" <<'EOF'
tool_policies:
  issue-sync-commit:
    enabled: true
    hook_timeout_seconds: 5
    commit_hook_mode: background
EOF
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"reserved"* ]]
}

# --- create flow non-interactive (FR-009) -----------------------------------

@test "no linked issue + non-interactive defaults to no-create" {
    git checkout -q -b hotfix-adhoc
    ISSUE_SUPPORT_INTERACTIVE=0 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"create-issue"*"skipped"* ]]
}

@test "no linked issue but a matching one exists → reuse + sync that issue (FR-009a/c)" {
    git checkout -q -b hotfix-adhoc
    mk_issue 5 open planned
    ISSUE_LIST_OUT="#5  hotfix-adhoc work" run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"existing match reused: #5"* ]] || return 1
    # FR-009c: the reused issue immediately enters the sync lifecycle
    [[ "$output" == *"#5 transition planned→in-progress"* ]]
}

@test "PR body already containing Closes #N is detected (no duplicate append)" {
    mk_issue 17 open planned
    printf '{"body":"Implements the thing. Closes #17"}' > "$FIXTURE_DIR/pr.json"
    run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
    [[ "$output" == *"closing-keyword Closes #17 [skipped] (already present)"* ]]
}

# --- FR-017: a failed run is recoverable on re-run --------------------------

@test "transition records [failed] when tracker errors, [applied] on a clean re-run" {
    mk_issue 17 open planned
    EDIT_RC=1 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"transition planned→in-progress [failed]"* ]] || return 1
    EDIT_RC=0 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"transition planned→in-progress [applied]"* ]]
}

# --- Task 7: transition_issue/comment_backlink re-pointed onto tracker_ops.sh -

@test "transition_issue shells out to tracker_ops issue-transition N target" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    grep -q "issue-transition 17 in-progress" "$CALL_LOG" || return 1
    [[ "$output" == *"#17 transition planned→in-progress [applied]"* ]]
}

@test "comment_backlink shells out to tracker_ops issue-comment N TEXT" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    grep -q "issue-comment 17 Work in progress" "$CALL_LOG" || return 1
    [[ "$output" == *"#17 comment back-link [applied]"* ]]
}

@test "detect_platform resolves via tracker_ops resolve-provider" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    grep -q "^resolve-provider" "$CALL_LOG" || return 1
}

@test "transition_issue fail-open on tracker rc=3 (jira-style MCP-only): returns 0, logs reason once (not double-printed), does not mark [failed]" {
    mk_issue 17 open planned
    TRACKER_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=3)"* ]] || return 1
    # the raw tracker_ops stderr ("unsupported-in-context") is captured, not
    # streamed live — the clean err() message above is the only surfaced text.
    [[ "$output" != *"unsupported-in-context"* ]] || return 1
    [[ "$output" != *"transition planned→in-progress [failed]"* ]]
}

@test "transition_issue fail-open on tracker rc=4 (verb not implemented): returns 0, logs reason once, does not mark [failed]" {
    mk_issue 17 open planned
    TRACKER_RC=4 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=4)"* ]] || return 1
    [[ "$output" != *"unsupported-in-context"* ]] || return 1
    [[ "$output" != *"transition planned→in-progress [failed]"* ]]
}

@test "comment_backlink fail-open on tracker rc=3: returns 0, logs reason, does not mark [failed]" {
    mk_issue 17 open planned
    TRACKER_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=3)"* ]] || return 1
    [[ "$output" != *"comment back-link [failed]"* ]]
}

@test "comment_backlink fail-open on tracker rc=4: returns 0, logs reason, does not mark [failed]" {
    mk_issue 17 open planned
    TRACKER_RC=4 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=4)"* ]] || return 1
    [[ "$output" != *"comment back-link [failed]"* ]]
}

# --- Fix round: suppress success-path leak; surface genuine failures; log fail-open skips ---

@test "successful transition+comment do not leak tracker_ops stdout URLs (Task 7 finding regression)" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" != *"https://github.com/example/repo/issues"* ]] || return 1
    [[ "$output" == *"transition planned→in-progress [applied]"* ]] || return 1
    [[ "$output" == *"comment back-link [applied]"* ]]
}

@test "transition_issue genuine (non-3/4) failure surfaces captured tracker diagnostic text" {
    mk_issue 17 open planned
    EDIT_RC=2 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"transition planned→in-progress [failed]"* ]] || return 1
    [[ "$output" == *"simulated genuine error"* ]]
}

@test "comment_backlink genuine (non-3/4) failure surfaces captured tracker diagnostic text" {
    mk_issue 17 open planned
    COMMENT_RC=2 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"comment back-link [failed]"* ]] || return 1
    [[ "$output" == *"simulated genuine error"* ]]
}

@test "transition_issue fail-open path records a record_action entry (not silently missing from summary)" {
    mk_issue 17 open planned
    TRACKER_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"#17 transition planned→in-progress [skipped] (tracker provider limitation, rc=3)"* ]]
}

@test "comment_backlink fail-open path records a record_action entry (not silently missing from summary)" {
    mk_issue 17 open planned
    TRACKER_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"#17 comment back-link [skipped] (tracker provider limitation, rc=3)"* ]]
}
