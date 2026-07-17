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
