#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/issue_support.sh
# Engine guarantees: resolution precedence, fail-open, idempotency, forward-only
# transitions, closed/locked skip, enabled gate, create-flow, background fallback.

SCRIPT="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/issue_support.sh"

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

    # Forge contract: TRACKER_OPS / git_platform.sh are hardcoded sibling
    # paths — the *_BIN stub seams no longer exist. Platform is pinned through
    # the real resolution order instead: MANIFEST_TRACKER env (override to
    # gitlab/jira per-test), falling back to the registry default (github).
    export MANIFEST_TRACKER=github

    # Native CLI fakes emit fixtures and record provider commands. The real
    # tracker_ops.sh relays to these, so a nonzero RC here surfaces exactly as
    # a tracker_ops failure upstream: rc 3/4 are the "provider limitation"
    # contract the engine treats as fail-open, anything else is a genuine
    # error. Both need diagnostic text on stderr — tracker_ops relays
    # stderr verbatim to the engine's captured-out.
    mkdir -p "$TMP/bin"
    cat >"$TMP/bin/forge-cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$1 ${2:-}" in
  "issue view") sub=issue-view; n="${3:-}" ;;
  "issue list") sub=issue-list ;;
  "issue edit"|"issue update") sub=issue-edit; n="${3:-}" ;;
  "issue comment"|"issue note") sub=issue-comment; n="${3:-}" ;;
  "issue create") sub=issue-create ;;
  "pr view"|"mr view") sub=pr-view ;;
  "pr edit"|"mr update") sub=pr-edit ;;
  *) sub="$1-${2:-}" ;;
esac
printf '%s %s\n' "$sub" "$*" >> "${CALL_LOG:-/dev/null}"
fail() {
    case "${2:-0}" in
        3|4) echo "tracker-ops: unsupported-in-context: simulated provider limitation" >&2 ;;
        *)   echo "tracker-ops: $1 failed: simulated genuine error" >&2 ;;
    esac
    exit "${2:-1}"
}
case "$sub" in
  issue-view) if [[ -f "${FIXTURE_DIR}/issue-${n}.json" ]]; then cat "${FIXTURE_DIR}/issue-${n}.json"; fi ;;
  pr-view) [[ -f "${FIXTURE_DIR}/pr.json" ]] && cat "${FIXTURE_DIR}/pr.json" || true ;;
  issue-list) printf '%s' "${ISSUE_LIST_OUT:-}" ;;
  issue-edit) [[ "${EDIT_RC:-0}" -eq 0 ]] || fail issue-edit "$EDIT_RC"; echo "https://github.com/example/repo/issues/${n}" ;;
  issue-comment) [[ "${COMMENT_RC:-0}" -eq 0 ]] || fail issue-comment "$COMMENT_RC"; echo "https://github.com/example/repo/issues/${n}#issuecomment-1" ;;
  issue-create) [[ "${CREATE_RC:-0}" -eq 0 ]] || fail issue-create "$CREATE_RC" ;;
  pr-edit) [[ "${PREDIT_RC:-0}" -eq 0 ]] || fail pr-edit "$PREDIT_RC" ;;
  *) exit "${NATIVE_CLI_RC:-0}" ;;
esac
EOF
    chmod +x "$TMP/bin/forge-cli"
    ln -s forge-cli "$TMP/bin/gh"
    ln -s forge-cli "$TMP/bin/glab"
    export PATH="$TMP/bin:$PATH"
    export CALL_LOG="$TMP/calls.log"

    # Isolate the user-scope opt-in overlay (T051). It defaults to
    # ~/.config/manifest/forge/issue_hooks.json, so without this a developer
    # who has opted in — or a previous test run that leaked — silently
    # overrides the fixture below and these tests read the machine, not the
    # fixture.
    export ISSUE_HOOKS_STATE="$TMP/issue_hooks.json"

    # Config with both skills enabled. Forge reads JSON tool_policies via
    # ISSUE_SUPPORT_CONFIG (the configs twin's YAML form is gone).
    export ISSUE_SUPPORT_CONFIG="$TMP/config.json"
    cat >"$ISSUE_SUPPORT_CONFIG" <<'EOF'
{"tool_policies": {
  "issue-sync-pr": {"enabled": true, "hook_timeout_seconds": 5},
  "issue-sync-commit": {"enabled": true, "hook_timeout_seconds": 5, "commit_hook_mode": "sync"}
}}
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
    NATIVE_CLI_RC=1 EDIT_RC=1 COMMENT_RC=1 run "$SCRIPT" sync-pr 42
    [ "$status" -eq 0 ]
}

@test "sync-commit exits 0 when the provider is non-GitHub/GitLab (no-op)" {
    # jira is a valid provider but MCP-only; detect_platform returns it and
    # sync_core short-circuits before any tracker call.
    MANIFEST_TRACKER=jira run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [ ! -s "$CALL_LOG" ]
}

# --- enabled gate (FR-015) --------------------------------------------------

@test "sync-pr is a no-op when disabled" {
    cat >"$ISSUE_SUPPORT_CONFIG" <<'EOF'
{"tool_policies": {
  "issue-sync-pr": {"enabled": false}
}}
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
{"tool_policies": {
  "issue-sync-commit": {"enabled": true, "hook_timeout_seconds": 5, "commit_hook_mode": "background"}
}}
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

@test "transition_issue applies the target via tracker_ops (gh issue edit label swap)" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    # The real tracker_ops relays issue-transition to `gh issue edit` with a
    # lifecycle label swap (remove every canonical label but the target).
    grep -q "issue-edit issue edit 17 --remove-label planned --remove-label needs-review --remove-label done --add-label in-progress" "$CALL_LOG" || return 1
    [[ "$output" == *"#17 transition planned→in-progress [applied]"* ]]
}

@test "comment_backlink applies the back-link via tracker_ops (gh issue comment --body)" {
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    grep -q "issue-comment issue comment 17 --body Work in progress on branch" "$CALL_LOG" || return 1
    [[ "$output" == *"#17 comment back-link [applied]"* ]]
}

@test "detect_platform honors the resolved provider (gitlab routes to glab note)" {
    # Forge runs the real tracker_ops.sh; MANIFEST_TRACKER=gitlab makes
    # resolve-provider return gitlab, so comments must go through
    # `glab issue note ... --message` rather than `gh issue comment --body`.
    export MANIFEST_TRACKER=gitlab
    mk_issue 17 open planned
    run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    grep -q "issue-comment issue note 17 --message" "$CALL_LOG" || return 1
    ! grep -q -- "--body" "$CALL_LOG"
}

@test "transition_issue fail-open on tracker rc=3 (provider limitation): returns 0, logs reason once (not double-printed), does not mark [failed]" {
    mk_issue 17 open planned
    EDIT_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=3)"* ]] || return 1
    # the raw tracker_ops stderr ("unsupported-in-context") is captured, not
    # streamed live — the clean err() message above is the only surfaced text.
    [[ "$output" != *"unsupported-in-context"* ]] || return 1
    [[ "$output" != *"transition planned→in-progress [failed]"* ]]
}

@test "transition_issue fail-open on tracker rc=4 (verb not implemented): returns 0, logs reason once, does not mark [failed]" {
    mk_issue 17 open planned
    EDIT_RC=4 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=4)"* ]] || return 1
    [[ "$output" != *"unsupported-in-context"* ]] || return 1
    [[ "$output" != *"transition planned→in-progress [failed]"* ]]
}

@test "comment_backlink fail-open on tracker rc=3: returns 0, logs reason, does not mark [failed]" {
    mk_issue 17 open planned
    COMMENT_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"tracker provider limitation (rc=3)"* ]] || return 1
    [[ "$output" != *"comment back-link [failed]"* ]]
}

@test "comment_backlink fail-open on tracker rc=4: returns 0, logs reason, does not mark [failed]" {
    mk_issue 17 open planned
    COMMENT_RC=4 run "$SCRIPT" sync-commit HEAD
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
    EDIT_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"#17 transition planned→in-progress [skipped] (tracker provider limitation, rc=3)"* ]]
}

@test "comment_backlink fail-open path records a record_action entry (not silently missing from summary)" {
    mk_issue 17 open planned
    COMMENT_RC=3 run "$SCRIPT" sync-commit HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"#17 comment back-link [skipped] (tracker provider limitation, rc=3)"* ]]
}
