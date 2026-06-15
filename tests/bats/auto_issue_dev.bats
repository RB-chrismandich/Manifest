#!/usr/bin/env bats
# Tests for configs/claude/scripts/auto_issue_dev.sh

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/auto_issue_dev.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/auto_issue_dev.XXXXXX")
    export FIXTURE_DIR="$TMP/fixtures"; mkdir -p "$FIXTURE_DIR"

    # Stub git_ops.sh: emit fixtures, log calls (with full flags), honor *_RC.
    # issue-view emits the fixture JSON regardless of format flags but the call
    # (incl. --json/--output/--comments) is logged so tests can assert flags.
    cat >"$TMP/git_ops.sh" <<'EOF'
#!/usr/bin/env bash
sub="$1"; shift
echo "$sub $*" >> "${CALL_LOG:-/dev/null}"
case "$sub" in
  issue-view)
    n="$1"
    # `--comments` (gitlab notes text) → emit the comment-text fixture if present
    if [[ " $* " == *" --comments "* ]]; then
      [[ -f "${FIXTURE_DIR}/comments-${n}.txt" ]] && cat "${FIXTURE_DIR}/comments-${n}.txt" || true
    else
      [[ -f "${FIXTURE_DIR}/issue-${n}.json" ]] && cat "${FIXTURE_DIR}/issue-${n}.json" || true
    fi
    ;;
  pr-view)     n="$1"; [[ -f "${FIXTURE_DIR}/pr-${n}.json" ]] && cat "${FIXTURE_DIR}/pr-${n}.json" || true ;;
  issue-list)  printf '%s' "${ISSUE_LIST_OUT:-[]}" ;;
  issue-edit)    exit "${EDIT_RC:-0}" ;;
  issue-comment) exit "${COMMENT_RC:-0}" ;;
  *) exit "${GITOPS_RC:-0}" ;;
esac
EOF
    chmod +x "$TMP/git_ops.sh"
    cat >"$TMP/git_platform.sh" <<'EOF'
#!/usr/bin/env bash
echo "${STUB_PLATFORM:-github}"
EOF
    chmod +x "$TMP/git_platform.sh"
    export GIT_OPS_BIN="$TMP/git_ops.sh"
    export GIT_PLATFORM_BIN="$TMP/git_platform.sh"
    export CALL_LOG="$TMP/calls.log"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# fixture writers
mk_issue() { # mk_issue <n> <state> <labels-csv> <body>
    local n="$1" state="$2" labels="$3" body="${4:-}"
    local lj=""; IFS=',' read -ra arr <<< "$labels"
    for l in "${arr[@]}"; do [[ -z "$l" ]] && continue; lj+="{\"name\":\"$l\"},"; done
    lj="[${lj%,}]"
    cat >"$FIXTURE_DIR/issue-$n.json" <<EOF
{"number":$n,"state":"$state","labels":$lj,"title":"issue $n","body":"$body","comments":[]}
EOF
}

@test "--help exits 0 and prints usage" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"next-issue"* ]]
    [[ "$output" == *"check-deps"* ]]
}

@test "unknown subcommand errors via err() and exits non-zero" {
    run "$SCRIPT" bogus
    [ "$status" -ne 0 ]
    [[ "$output" == *"auto-issue-dev:"* ]]
}

@test "check-deps: no dependency refs -> exit 0" {
    mk_issue 10 open auto-dev "Just a normal issue body"
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
}

@test "check-deps: 'blocked by #11' where #11 open -> exit 2, names ref" {
    mk_issue 10 open auto-dev "blocked by #11"
    mk_issue 11 open "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
    [[ "$output" == *"#11"* ]]
}

@test "check-deps: 'depends on #11' where #11 closed -> exit 0" {
    mk_issue 10 open auto-dev "depends on #11"
    mk_issue 11 closed "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
}

@test "check-deps: multiple patterns, mix of met/unmet -> exit 2 lists only unmet" {
    mk_issue 10 open auto-dev "requires #11 and needs #12"
    mk_issue 11 closed "" ""
    mk_issue 12 open "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
    [[ "$output" == *"#12"* ]]
    [[ "$output" != *"#11"* ]]
}

@test "mark-blocked: adds needs-human label and a comment, exit 0" {
    mk_issue 10 open auto-dev ""
    run "$SCRIPT" mark-blocked 10 "tests failed"
    [ "$status" -eq 0 ]
    grep -q "issue-edit 10 .*needs-human" "$CALL_LOG"
    grep -q "issue-comment 10" "$CALL_LOG"
}

@test "mark-blocked: skips comment when marker already present (dedup)" {
    cat >"$FIXTURE_DIR/issue-10.json" <<'EOF'
{"number":10,"state":"open","labels":[{"name":"auto-dev"}],"title":"t","body":"b","comments":[{"body":"<!-- auto-issue-dev:blocked -->\nprior"}]}
EOF
    run "$SCRIPT" mark-blocked 10 "again"
    [ "$status" -eq 0 ]
    ! grep -q "issue-comment 10" "$CALL_LOG"
}

@test "mark-blocked: fail-open when label edit errors" {
    mk_issue 10 open auto-dev ""
    EDIT_RC=1 run "$SCRIPT" mark-blocked 10 "reason"
    [ "$status" -eq 0 ]
}

@test "mark-dependency: adds blocked-dependency label + comment naming refs" {
    mk_issue 10 open auto-dev ""
    run "$SCRIPT" mark-dependency 10 "#11 #12"
    [ "$status" -eq 0 ]
    grep -q "issue-edit 10 .*blocked-dependency" "$CALL_LOG"
    grep -q "issue-comment 10" "$CALL_LOG"
}

@test "next-issue: returns lowest-numbered ready auto-dev issue (JSON)" {
    export ISSUE_LIST_OUT='[{"number":21,"title":"b","url":"u21","labels":[{"name":"auto-dev"}]},{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"}]}]'
    mk_issue 20 open auto-dev "no deps"
    mk_issue 21 open auto-dev "no deps"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":20'* ]]
}

@test "next-issue: skips + tags a dependency-blocked candidate, returns next ready" {
    export ISSUE_LIST_OUT='[{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"}]},{"number":21,"title":"b","url":"u21","labels":[{"name":"auto-dev"}]}]'
    mk_issue 20 open auto-dev "blocked by #99"
    mk_issue 99 open "" ""
    mk_issue 21 open auto-dev "ready"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":21'* ]]
    [[ "$output" == *'"skipped_dependency":1'* ]]
    grep -q "issue-edit 20 .*blocked-dependency" "$CALL_LOG"
}

@test "next-issue: pre-excludes already blocked-dependency-tagged issues" {
    export ISSUE_LIST_OUT='[{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"},{"name":"blocked-dependency"}]}]'
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 3 ]
    [[ "$output" == *'"skipped_other":1'* ]]
}

@test "next-issue: empty queue -> exit 3 with counts" {
    export ISSUE_LIST_OUT='[]'
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 3 ]
    [[ "$output" == *'"ready":0'* ]]
    [[ "$output" == *'"skipped_dependency":0'* ]]
}

# --- regression: format flags are actually passed (the original bug) ---------

@test "check-deps (github): passes --json on issue-view" {
    mk_issue 10 open auto-dev "no deps"
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
    grep -q "issue-view 10 .*--json" "$CALL_LOG"
}

@test "next-issue (github): passes --json on issue-list and issue-view" {
    export ISSUE_LIST_OUT='[{"number":30,"title":"a","url":"u30","labels":[{"name":"auto-dev"}]}]'
    mk_issue 30 open auto-dev "ready"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    grep -q "issue-list .*--json" "$CALL_LOG"
    grep -q "issue-view 30 .*--json" "$CALL_LOG"
}

# --- GitLab platform variant -------------------------------------------------

@test "check-deps (gitlab): uses --output json and parses iid/description/opened" {
    export STUB_PLATFORM=gitlab
    # gitlab-shaped issue: iid (not number), description (not body), opened state
    cat >"$FIXTURE_DIR/issue-40.json" <<'EOF'
{"iid":40,"state":"opened","labels":["auto-dev"],"title":"gl issue","description":"blocked by #41"}
EOF
    # blocker #41 still opened (unmet)
    cat >"$FIXTURE_DIR/issue-41.json" <<'EOF'
{"iid":41,"state":"opened","labels":[],"title":"blocker","description":""}
EOF
    run "$SCRIPT" check-deps 40
    [ "$status" -eq 2 ]
    [[ "$output" == *"#41"* ]]
    grep -q "issue-view 40 --output json" "$CALL_LOG"
}

@test "next-issue (gitlab): uses --output json for issue-list" {
    export STUB_PLATFORM=gitlab
    export ISSUE_LIST_OUT='[{"iid":50,"title":"gl","web_url":"w50","labels":["auto-dev"]}]'
    cat >"$FIXTURE_DIR/issue-50.json" <<'EOF'
{"iid":50,"state":"opened","labels":["auto-dev"],"title":"gl","description":"ready"}
EOF
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":50'* ]]
    grep -q "issue-list .*--output json" "$CALL_LOG"
}

# --- ref_met PR-merged fallback ----------------------------------------------

@test "check-deps: dependency PR merged (no issue) -> exit 0" {
    mk_issue 10 open auto-dev "blocked by #99"
    # no issue-99.json (issue-view empty) -> falls back to PR view
    cat >"$FIXTURE_DIR/pr-99.json" <<'EOF'
{"state":"merged","merged":true}
EOF
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
}

# --- mark-dependency dedup (symmetric to mark-blocked dedup) ------------------

@test "mark-dependency: skips comment when marker already present (dedup)" {
    cat >"$FIXTURE_DIR/issue-10.json" <<'EOF'
{"number":10,"state":"open","labels":[{"name":"auto-dev"}],"title":"t","body":"b","comments":[{"body":"<!-- auto-issue-dev:dependency -->\nprior"}]}
EOF
    run "$SCRIPT" mark-dependency 10 "#11"
    [ "$status" -eq 0 ]
    ! grep -q "issue-comment 10" "$CALL_LOG"
}

# --- ref_met pr-view requests JSON (FIX 1) -----------------------------------

@test "check-deps (github): pr-view fallback passes a JSON flag, merged -> exit 0" {
    mk_issue 10 open auto-dev "blocked by #99"
    cat >"$FIXTURE_DIR/pr-99.json" <<'EOF'
{"state":"MERGED","merged":true}
EOF
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
    grep -q "pr-view 99 --json" "$CALL_LOG"
}

@test "check-deps (github): dependency PR still open -> unmet exit 2" {
    mk_issue 10 open auto-dev "blocked by #99"
    cat >"$FIXTURE_DIR/pr-99.json" <<'EOF'
{"state":"OPEN","merged":false}
EOF
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
}

@test "check-deps: dangling ref (no issue, no PR fixture) -> unmet exit 2" {
    mk_issue 10 open auto-dev "blocked by #99"
    # no issue-99.json and no pr-99.json -> both views empty -> UNMET
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
}

# --- mark-* fail-open under double/comment failure ---------------------------

@test "mark-blocked: fail-open when both edit and comment error" {
    mk_issue 10 open auto-dev ""
    EDIT_RC=1 COMMENT_RC=1 run "$SCRIPT" mark-blocked 10 "boom"
    [ "$status" -eq 0 ]
}

@test "mark-dependency: fail-open when comment errors" {
    mk_issue 10 open auto-dev ""
    COMMENT_RC=1 run "$SCRIPT" mark-dependency 10 "#11"
    [ "$status" -eq 0 ]
}

# --- gitlab dedup via --comments notes text ---------------------------------

@test "mark-dependency (gitlab): dedup via --comments notes text" {
    export STUB_PLATFORM=gitlab
    cat >"$FIXTURE_DIR/issue-60.json" <<'EOF'
{"iid":60,"state":"opened","labels":["auto-dev"],"title":"t","description":"x"}
EOF
    printf '%s\n' '<!-- auto-issue-dev:dependency -->' 'prior' >"$FIXTURE_DIR/comments-60.txt"
    run "$SCRIPT" mark-dependency 60 "#61"
    [ "$status" -eq 0 ]
    grep -q "issue-view 60 --comments" "$CALL_LOG"
    ! grep -q "issue-comment 60" "$CALL_LOG"
}

# --- next-issue skipped_dependency count ------------------------------------

@test "next-issue: single dep-blocked candidate -> exit 3 with skipped_dependency:1" {
    export ISSUE_LIST_OUT='[{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"}]}]'
    mk_issue 20 open auto-dev "blocked by #99"
    mk_issue 99 open "" ""
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 3 ]
    [[ "$output" == *'"skipped_dependency":1'* ]]
}

# --- self-reference is skipped ----------------------------------------------

@test "check-deps: self-reference (#N depends on #N) -> exit 0" {
    mk_issue 10 open auto-dev "depends on #10"
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
}

# --- missing-arg -------------------------------------------------------------

@test "check-deps: missing issue number -> exit 1" {
    run "$SCRIPT" check-deps
    [ "$status" -eq 1 ]
    [[ "$output" == *"issue number required"* ]]
}

# --- requires-only unmet -----------------------------------------------------

@test "check-deps: 'requires #11' where #11 open -> exit 2 names #11" {
    mk_issue 10 open auto-dev "requires #11"
    mk_issue 11 open "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
    [[ "$output" == *"#11"* ]]
}

# --- Issue #358: unblock-aware prioritization --------------------------------

@test "next-issue: unblocking issue outranks isolated higher-severity issue" {
    # #20 priority:high, isolated; #21 no priority, but #22 #23 #24 all depend on it
    # new code must return #21 (unblocks 3 > 0), not #20 (lowest number / higher severity)
    export ISSUE_LIST_OUT='[{"number":20,"title":"highpri","url":"u20","labels":[{"name":"auto-dev"},{"name":"priority:high"}]},{"number":21,"title":"blocker","url":"u21","labels":[{"name":"auto-dev"}]},{"number":22,"title":"c","url":"u22","labels":[{"name":"auto-dev"}]},{"number":23,"title":"d","url":"u23","labels":[{"name":"auto-dev"}]},{"number":24,"title":"e","url":"u24","labels":[{"name":"auto-dev"}]}]'
    mk_issue 20 open "auto-dev,priority:high" "no deps"
    mk_issue 21 open auto-dev "no deps"
    mk_issue 22 open auto-dev "depends on #21"
    mk_issue 23 open auto-dev "blocked by #21"
    mk_issue 24 open auto-dev "requires #21"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":21'* ]]
    [[ "$output" == *'"reason":'* ]]
}

@test "next-issue: with no inter-issue deps, severity outranks issue number" {
    # #30 lower number (no priority); #31 higher number (priority:high)
    # current code returns #30; new code must return #31
    export ISSUE_LIST_OUT='[{"number":30,"title":"low","url":"u30","labels":[{"name":"auto-dev"}]},{"number":31,"title":"high","url":"u31","labels":[{"name":"auto-dev"},{"name":"priority:high"}]}]'
    mk_issue 30 open auto-dev "no deps"
    mk_issue 31 open "auto-dev,priority:high" "no deps"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":31'* ]]
}

@test "next-issue: JSON output always includes reason field" {
    export ISSUE_LIST_OUT='[{"number":40,"title":"a","url":"u40","labels":[{"name":"auto-dev"}]}]'
    mk_issue 40 open auto-dev "no deps"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"reason":'* ]]
}

@test "next-issue: ordering is deterministic across repeated runs" {
    export ISSUE_LIST_OUT='[{"number":50,"title":"a","url":"u50","labels":[{"name":"auto-dev"}]},{"number":51,"title":"b","url":"u51","labels":[{"name":"auto-dev"}]}]'
    mk_issue 50 open auto-dev "no deps"
    mk_issue 51 open auto-dev "no deps"
    run "$SCRIPT" next-issue --json
    local first_out="$output"
    run "$SCRIPT" next-issue --json
    [ "$output" = "$first_out" ]
}

@test "next-issue: dependency cycle is surfaced in output" {
    # #60 depends on #61; #61 depends on #60 → mutual cycle should appear in output
    export ISSUE_LIST_OUT='[{"number":60,"title":"a","url":"u60","labels":[{"name":"auto-dev"}]},{"number":61,"title":"b","url":"u61","labels":[{"name":"auto-dev"}]}]'
    mk_issue 60 open auto-dev "depends on #61"
    mk_issue 61 open auto-dev "depends on #60"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 3 ]
    [[ "$output" == *'cycle'* ]]
}
