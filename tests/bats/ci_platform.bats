#!/usr/bin/env bats
# Tests for configs/claude/scripts/ci_platform.sh
# CI platform detection from repo config files, env var override,
# and both-present tie-break via git_platform.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../configs/claude/scripts/ci_platform.sh"

setup() {
    # Create a temporary directory for each test
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_REPO=$(mktemp -d "$BATS_TMPDIR/ci_platform_test.XXXXXX")

    # Initialize a git repo so git_platform.sh has something to inspect
    git init "$TEST_REPO" > /dev/null 2>&1
    cd "$TEST_REPO" || return 1

    # Clear any override env vars
    unset MANIFEST_CI_PLATFORM
    unset MANIFEST_GIT_PLATFORM
    unset MANIFEST_GIT_REMOTE
}

teardown() {
    # Clean up temporary repo
    if [[ -n "$TEST_REPO" && -d "$TEST_REPO" ]]; then
        rm -rf "$TEST_REPO"
    fi
}

# --- Environment variable override tests ---

@test "MANIFEST_CI_PLATFORM=github-actions overrides detection" {
    export MANIFEST_CI_PLATFORM="github-actions"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
}

@test "MANIFEST_CI_PLATFORM=gitlab-ci overrides detection" {
    export MANIFEST_CI_PLATFORM="gitlab-ci"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab-ci"
}

@test "MANIFEST_CI_PLATFORM=none overrides detection" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    export MANIFEST_CI_PLATFORM="none"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "none"
}

@test "MANIFEST_CI_PLATFORM with invalid value fails" {
    export MANIFEST_CI_PLATFORM="jenkins"
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "Invalid MANIFEST_CI_PLATFORM"
}

# --- Single-platform detection tests ---

@test "detects github-actions from .github/workflows/*.yml" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
}

@test "detects github-actions from .github/workflows/*.yaml" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yaml
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
}

@test "detects gitlab-ci from .gitlab-ci.yml" {
    echo "stages: [test]" > .gitlab-ci.yml
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab-ci"
}

@test "returns none when neither CI config is present" {
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "none"
}

@test "empty .github/workflows dir with no yml files does not count as github-actions" {
    mkdir -p .github/workflows
    echo "stages: [test]" > .gitlab-ci.yml
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab-ci"
}

# --- Both-present tie-break tests (prefer git_platform.sh's match) ---

@test "both present + github.com remote prefers github-actions" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    echo "stages: [test]" > .gitlab-ci.yml
    git remote add origin "https://github.com/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
}

@test "both present + gitlab.com remote prefers gitlab-ci" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    echo "stages: [test]" > .gitlab-ci.yml
    git remote add origin "https://gitlab.com/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab-ci"
}

@test "both present + plain git remote (no github/gitlab match) falls back deterministically" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    echo "stages: [test]" > .gitlab-ci.yml
    git remote add origin "https://bitbucket.org/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
}

@test "both present + no remote at all (git_platform.sh fails) falls back deterministically" {
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    echo "stages: [test]" > .gitlab-ci.yml
    # No remote added, so git_platform.sh exits 1 with "Remote 'origin' not found"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
}

@test "both present + not a git repo at all falls back deterministically" {
    NON_GIT_DIR=$(mktemp -d "$BATS_TMPDIR/ci_platform_nongit.XXXXXX")
    cd "$NON_GIT_DIR" || return 1
    mkdir -p .github/workflows
    echo "name: ci" > .github/workflows/ci.yml
    echo "stages: [test]" > .gitlab-ci.yml
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github-actions"
    rm -rf "$NON_GIT_DIR"
}
