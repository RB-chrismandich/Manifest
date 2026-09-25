setup() {
    SCRIPT="${BATS_TEST_DIRNAME}/../../plugins/manifest-forge/runtime/bin/tracker_ops.sh"
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

# Forge tracker_ops.sh hard-dispatches to its bundled linear_ops.sh (no
# LINEAR_OPS_BIN seam), so linear delegation is observed through the Linear
# HTTP engine: a curl stub that logs each GraphQL payload and returns canned
# responses for issue-view / workflowStates / commentCreate / issueUpdate.
make_linear_api_stub() {
    export LINEAR_API_LOG="${STUBS}/linear-api.calls"
    : > "${LINEAR_API_LOG}"
    cat > "${STUBS}/curl" <<'EOS'
#!/usr/bin/env bash
body=""
while (($#)); do
    case "$1" in -d) body="$2"; shift 2 ;; *) shift ;; esac
done
printf '%s\n' "$body" >> "$LINEAR_API_LOG"
name=$(printf '%s' "$body" | jq -r '.variables.filter.name.eq // empty' 2>/dev/null)
query=$(printf '%s' "$body" | jq -r '.query')
case "$query" in
    *workflowStates*)
        state="${name:-In Review}"
        stype=started sid=state-x
        [[ "$state" == "Canceled" ]] && { stype=canceled; sid=state-canceled; }
        [[ "$state" == "In Review" ]] && sid=state-review
        printf '{"data":{"workflowStates":{"nodes":[{"id":"%s","name":"%s","type":"%s"}]}}}\n' "$sid" "$state" "$stype"
        ;;
    *commentCreate*)
        printf '{"data":{"commentCreate":{"success":true,"comment":{"id":"c1"}}}}\n'
        ;;
    *issueUpdate*)
        printf '{"data":{"issueUpdate":{"success":true,"issue":{"id":"i1","identifier":"ENG-42","state":{"name":"In Review","type":"started"}}}}}\n'
        ;;
    *)
        printf '{"data":{"issue":{"id":"i1","identifier":"ENG-42","title":"t","state":{"name":"In Progress","type":"started"},"team":{"id":"t1","key":"ENG","name":"Eng"}}}}\n'
        ;;
esac
EOS
    chmod +x "${STUBS}/curl"
    export LINEAR_API_KEY="test-token"
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
    make_linear_api_stub
    MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-close ENG-42
    [ "$status" -eq 0 ]
    # issue lookup for ENG-42, Canceled-state resolution, then issueUpdate.
    grep -q '"identifier":"ENG-42"' "${LINEAR_API_LOG}"
    grep -q '"eq":"Canceled"' "${LINEAR_API_LOG}"
    grep -q 'issueUpdate' "${LINEAR_API_LOG}"
}

@test "issue-comment on linear translates positional TEXT into --body (bug: linear_ops.sh has no positional support)" {
    make_linear_api_stub
    MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-comment ENG-42 "some text"
    [ "$status" -eq 0 ]
    # commentCreate mutation carries the positional text as its body.
    grep -q 'commentCreate' "${LINEAR_API_LOG}"
    grep -q '"body":"some text"' "${LINEAR_API_LOG}"
}

@test "issue-comment on linear passes already-flag-style --body through unchanged" {
    make_linear_api_stub
    MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-comment ENG-42 --body "some text"
    [ "$status" -eq 0 ]
    grep -q 'commentCreate' "${LINEAR_API_LOG}"
    grep -q '"body":"some text"' "${LINEAR_API_LOG}"
    # exactly one commentCreate call, not a double-wrapped body
    [ "$(grep -c 'commentCreate' "${LINEAR_API_LOG}")" = "1" ]
}

@test "issue-comment on linear does not wrap TEXT that itself starts with a dash" {
    make_linear_api_stub
    MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-comment ENG-42 "-not-a-flag"
    # Passed through verbatim: linear_ops rejects it as an unknown option.
    [ "$status" -ne 0 ]
    ! grep -q 'commentCreate' "${LINEAR_API_LOG}"
    [[ "$output" == *"Unknown option: -not-a-flag"* ]]
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
    make_linear_api_stub
    MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-transition ENG-42 needs-review
    [ "$status" -eq 0 ]
    # Canonical needs-review maps to the Linear workflow state "In Review"
    # (resolved by name via workflowStates) before the issueUpdate mutation.
    grep -q 'workflowStates' "${LINEAR_API_LOG}"
    grep -q '"eq":"In Review"' "${LINEAR_API_LOG}"
    grep -q 'issueUpdate' "${LINEAR_API_LOG}"
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
