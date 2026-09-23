setup() {
    SCRIPT="${BATS_TEST_DIRNAME}/../../configs/claude/scripts/tracker_ops.sh"
    TMPDIR_T="$(mktemp -d)"
    STUBS="${TMPDIR_T}/stubs"; mkdir -p "${STUBS}"
    PATH="${STUBS}:${PATH}"
    export MANIFEST_GIT_PLATFORM=git   # neutralize remote detection by default
    WORKDIR="${TMPDIR_T}/work"; mkdir -p "${WORKDIR}"
    cd "${WORKDIR}"
}

teardown() { rm -rf "${TMPDIR_T}"; }

@test "help exits 0 before any config lookup" {
    run bash "${SCRIPT}" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "MANIFEST_TRACKER env overrides detection" {
    MANIFEST_TRACKER=linear run bash "${SCRIPT}" resolve-provider
    [ "$status" -eq 0 ]
    [ "$output" = "linear" ]
}

@test "marker file beats remote detection" {
    REPO="${TMPDIR_T}/repo"; mkdir -p "${REPO}"
    cd "${REPO}" && git init -q .
    echo "jira" > .manifest-tracker
    run bash "${SCRIPT}" resolve-provider
    [ "$status" -eq 0 ]
    [ "$output" = "jira" ]
}

@test "github remote resolves to github" {
    unset MANIFEST_GIT_PLATFORM
    MANIFEST_GIT_PLATFORM=github run bash "${SCRIPT}" resolve-provider
    [ "$output" = "github" ]
}

@test "plain git falls through to registry default" {
    run bash "${SCRIPT}" resolve-provider
    [ "$status" -eq 0 ]
    [ "$output" = "github" ]   # default_provider in registry
}

@test "invalid provider name rejected" {
    MANIFEST_TRACKER=bitbucket run bash "${SCRIPT}" resolve-provider
    [ "$status" -ne 0 ]
    [[ "$output" == *"bitbucket"* ]]
}

make_stub() { # $1=path — records argv to ${1}.calls
    cat > "$1" << 'EOS'
#!/usr/bin/env bash
echo "$@" >> "${0}.calls"
EOS
    chmod +x "$1"
}

make_native_stub() { # $1=native command assertion log path
    export NATIVE_CALL_LOG="$1"
    cat > "${STUBS}/gh" <<'EOS'
#!/usr/bin/env bash
printf 'argc=%d' "$#" >> "$NATIVE_CALL_LOG"
printf ' %q' "$@" >> "$NATIVE_CALL_LOG"
printf '\n' >> "$NATIVE_CALL_LOG"
exit "${NATIVE_CLI_RC:-0}"
EOS
    chmod +x "${STUBS}/gh"
    ln -sf gh "${STUBS}/glab"
}

@test "issue-list on github calls gh issue list" {
    make_native_stub "${STUBS}/native-cli.calls"
    MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-list --limit 5
    [ "$status" -eq 0 ]
    grep -q "issue list --limit 5" "${STUBS}/native-cli.calls"
}

@test "issue-close on linear delegates to linear_ops" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-close ENG-42
    [ "$status" -eq 0 ]
    grep -q "issue-close ENG-42" "${STUBS}/linear_ops.sh.calls"
}

@test "issue-comment on linear translates positional TEXT into --body (bug: linear_ops.sh has no positional support)" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-comment ENG-42 "some text"
    [ "$status" -eq 0 ]
    grep -q -- "issue-comment ENG-42 --body some text" "${STUBS}/linear_ops.sh.calls"
}

@test "issue-comment on linear passes already-flag-style --body through unchanged" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-comment ENG-42 --body "some text"
    [ "$status" -eq 0 ]
    grep -q -- "issue-comment ENG-42 --body some text" "${STUBS}/linear_ops.sh.calls"
    # exactly one --body, not double-wrapped
    [ "$(grep -o -- "--body" "${STUBS}/linear_ops.sh.calls" | wc -l | tr -d ' ')" = "1" ]
}

@test "issue-comment on linear does not wrap TEXT that itself starts with a dash" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-comment ENG-42 "-not-a-flag"
    [ "$status" -eq 0 ]
    grep -q -- "issue-comment ENG-42 -not-a-flag" "${STUBS}/linear_ops.sh.calls"
}

@test "issue-comment on github calls gh issue comment with --body" {
    make_native_stub "${STUBS}/native-cli.calls"
    MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-comment 42 "some text"
    [ "$status" -eq 0 ]
    grep -Fq -- 'argc=5 issue comment 42 --body some\ text' "${STUBS}/native-cli.calls"
}

@test "issue-transition github calls gh issue edit with canonical labels" {
    make_native_stub "${STUBS}/native-cli.calls"
    MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-transition 7 needs-review
    [ "$status" -eq 0 ]
    grep -q -- "--add-label needs-review" "${STUBS}/native-cli.calls"
    grep -q -- "--remove-label planned" "${STUBS}/native-cli.calls"
}

@test "issue-transition linear uses workflow state name" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-transition ENG-42 needs-review
    grep -q -- "transition-state --identifier ENG-42 --state In Review" "${STUBS}/linear_ops.sh.calls"
}

@test "issue-transition missing args exits 1 with usage hint" {
    run bash "${SCRIPT}" --provider linear issue-transition
    [ "$status" -eq 1 ]
    [[ "$output" == *"usage:"* ]]
}

@test "issue-transition missing target exits 1 with usage hint" {
    run bash "${SCRIPT}" --provider linear issue-transition ENG-42
    [ "$status" -eq 1 ]
    [[ "$output" == *"usage:"* ]]
}

@test "duplicate-mark missing args exits 1 with usage hint" {
    run bash "${SCRIPT}" --provider linear duplicate-mark
    [ "$status" -eq 1 ]
    [[ "$output" == *"usage:"* ]]
}

@test "duplicate-mark missing --duplicate-of value exits 1 with usage hint" {
    run bash "${SCRIPT}" --provider linear duplicate-mark 9 --duplicate-of
    [ "$status" -eq 1 ]
    [[ "$output" == *"usage:"* ]]
}

@test "issue-label on linear exits 4 not-implemented" {
    MANIFEST_TRACKER=linear run bash "${SCRIPT}" issue-label ENG-42 --add-label bug
    [ "$status" -eq 4 ]
    [[ "$output" == *"not implemented"* ]]
}

@test "duplicate-mark github comments labels and closes natively" {
    make_native_stub "${STUBS}/native-cli.calls"
    MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" duplicate-mark 9 --duplicate-of 4
    grep -Fq 'argc=5 issue comment 9 --body Duplicate\ of\ #4' "${STUBS}/native-cli.calls"
    grep -q -- "issue edit 9 --add-label duplicate" "${STUBS}/native-cli.calls"
    grep -q "issue close 9" "${STUBS}/native-cli.calls"
}

@test "issue-transition gitlab uses native label flags" {
    make_native_stub "${STUBS}/native-cli.calls"
    MANIFEST_TRACKER=gitlab run bash "${SCRIPT}" issue-transition 7 needs-review
    [ "$status" -eq 0 ]
    grep -q -- "issue update 7 .*--unlabel planned.*--label needs-review" "${STUBS}/native-cli.calls"
}

@test "duplicate-mark gitlab uses native label flags" {
    make_native_stub "${STUBS}/native-cli.calls"
    MANIFEST_TRACKER=gitlab run bash "${SCRIPT}" duplicate-mark 9 --duplicate-of 4
    [ "$status" -eq 0 ]
    grep -q -- "issue update 9 --label duplicate" "${STUBS}/native-cli.calls"
}

@test "issue-comment preserves multiline shell text as one GitHub argv value" {
    make_native_stub "${STUBS}/native-cli.calls"
    body=$'line one\n"quoted"; $(not-run)'
    expected=$(printf '%q' "$body")
    MANIFEST_TRACKER=github run bash "${SCRIPT}" issue-comment 42 "$body"
    [ "$status" -eq 0 ]
    grep -Fq -- "argc=5 issue comment 42 --body ${expected}" "${STUBS}/native-cli.calls"
}

@test "issue-comment preserves multiline shell text as one GitLab argv value" {
    make_native_stub "${STUBS}/native-cli.calls"
    body=$'line one\n"quoted"; $(not-run)'
    expected=$(printf '%q' "$body")
    MANIFEST_TRACKER=gitlab run bash "${SCRIPT}" issue-comment 42 "$body"
    [ "$status" -eq 0 ]
    grep -Fq -- "argc=5 issue note 42 --message ${expected}" "${STUBS}/native-cli.calls"
}
@test "native CLI failure propagates from tracker operation" {
    make_native_stub "${STUBS}/native-cli.calls"
    NATIVE_CLI_RC=17 MANIFEST_TRACKER=github run bash "${SCRIPT}" issue-list
    [ "$status" -eq 17 ]
}


@test "jira from shell context exits 3 with distinct message" {
    MANIFEST_TRACKER=jira run bash "${SCRIPT}" issue-list
    [ "$status" -eq 3 ]
    [[ "$output" == *"unsupported-in-context"* ]]
}

@test "sub-issue-create on github exits 4 not-implemented" {
    MANIFEST_TRACKER=github run bash "${SCRIPT}" sub-issue-create
    [ "$status" -eq 4 ]
    [[ "$output" == *"not implemented"* ]]
}
