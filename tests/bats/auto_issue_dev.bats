#!/usr/bin/env bats
# Tests for configs/claude/scripts/auto_issue_dev.sh

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/auto_issue_dev.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/auto_issue_dev.XXXXXX")
    export FIXTURE_DIR="$TMP/fixtures"; mkdir -p "$FIXTURE_DIR"

    # Stub git_ops.sh: emit fixtures, log calls, honor *_RC
    cat >"$TMP/git_ops.sh" <<'EOF'
#!/usr/bin/env bash
sub="$1"; shift
echo "$sub $*" >> "${CALL_LOG:-/dev/null}"
case "$sub" in
  issue-view)  n="$1"; [[ -f "${FIXTURE_DIR}/issue-${n}.json" ]] && cat "${FIXTURE_DIR}/issue-${n}.json" || true ;;
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
