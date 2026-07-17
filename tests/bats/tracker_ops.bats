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

@test "issue-list on github delegates to git_ops" {
    make_stub "${STUBS}/git_ops.sh"
    GIT_OPS_BIN="${STUBS}/git_ops.sh" MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-list --limit 5
    [ "$status" -eq 0 ]
    grep -q "issue-list --limit 5" "${STUBS}/git_ops.sh.calls"
}

@test "issue-close on linear delegates to linear_ops" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-close ENG-42
    [ "$status" -eq 0 ]
    grep -q "issue-close ENG-42" "${STUBS}/linear_ops.sh.calls"
}

@test "issue-transition github swaps canonical labels" {
    make_stub "${STUBS}/git_ops.sh"
    GIT_OPS_BIN="${STUBS}/git_ops.sh" MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-transition 7 needs-review
    [ "$status" -eq 0 ]
    grep -q -- "--add-label needs-review" "${STUBS}/git_ops.sh.calls"
    grep -q -- "--remove-label planned" "${STUBS}/git_ops.sh.calls"
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

@test "duplicate-mark github closes with comment and label" {
    make_stub "${STUBS}/git_ops.sh"
    GIT_OPS_BIN="${STUBS}/git_ops.sh" MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" duplicate-mark 9 --duplicate-of 4
    grep -q "issue-comment 9 Duplicate of #4" "${STUBS}/git_ops.sh.calls"
    grep -q -- "issue-edit 9 --add-label duplicate" "${STUBS}/git_ops.sh.calls"
    grep -q "issue-close 9" "${STUBS}/git_ops.sh.calls"
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
