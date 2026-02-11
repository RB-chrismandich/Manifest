#!/usr/bin/env bats
# Tests for configs/claude/scripts/git_platform.sh
# Platform detection from remote URL, env var override, fallback behavior

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../configs/claude/scripts/git_platform.sh"

setup() {
    # Create a temporary directory for each test
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_REPO=$(mktemp -d "$BATS_TMPDIR/git_platform_test.XXXXXX")

    # Initialize a bare git repo with a remote
    git init "$TEST_REPO" > /dev/null 2>&1
    cd "$TEST_REPO" || return 1

    # Clear any override env vars
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

@test "MANIFEST_GIT_PLATFORM=github overrides detection" {
    export MANIFEST_GIT_PLATFORM="github"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github"
}

@test "MANIFEST_GIT_PLATFORM=gitlab overrides detection" {
    export MANIFEST_GIT_PLATFORM="gitlab"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab"
}

@test "MANIFEST_GIT_PLATFORM=git overrides detection" {
    export MANIFEST_GIT_PLATFORM="git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "git"
}

@test "MANIFEST_GIT_PLATFORM with invalid value fails" {
    export MANIFEST_GIT_PLATFORM="bitbucket"
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "Invalid MANIFEST_GIT_PLATFORM"
}

# --- Remote URL detection tests ---

@test "detects github.com HTTPS remote" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://github.com/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github"
}

@test "detects github.com SSH remote" {
    cd "$TEST_REPO" || return 1
    git remote add origin "git@github.com:user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "github"
}

@test "detects gitlab.com HTTPS remote" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://gitlab.com/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab"
}

@test "detects gitlab.com SSH remote" {
    cd "$TEST_REPO" || return 1
    git remote add origin "git@gitlab.com:user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab"
}

@test "detects self-hosted GitLab (gitlab.example.com)" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://gitlab.example.com/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab"
}

@test "falls back to git for unknown hosting platform" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://bitbucket.org/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "git"
}

@test "falls back to git for plain SSH remote" {
    cd "$TEST_REPO" || return 1
    git remote add origin "ssh://git@myserver.local/repo.git"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "git"
}

# --- Remote name argument tests ---

@test "uses custom remote name from argument" {
    cd "$TEST_REPO" || return 1
    git remote add upstream "https://gitlab.com/upstream/repo.git"
    run bash "$SCRIPT_UNDER_TEST" upstream
    assert_success
    assert_output "gitlab"
}

@test "MANIFEST_GIT_REMOTE env var selects remote" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://github.com/user/repo.git"
    git remote add upstream "https://gitlab.com/upstream/repo.git"
    export MANIFEST_GIT_REMOTE="upstream"
    run bash "$SCRIPT_UNDER_TEST"
    assert_success
    assert_output "gitlab"
}

@test "argument takes precedence over MANIFEST_GIT_REMOTE" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://github.com/user/repo.git"
    git remote add upstream "https://gitlab.com/upstream/repo.git"
    export MANIFEST_GIT_REMOTE="origin"
    run bash "$SCRIPT_UNDER_TEST" upstream
    assert_success
    assert_output "gitlab"
}

# --- Error handling tests ---

@test "fails when remote does not exist" {
    cd "$TEST_REPO" || return 1
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "Remote 'origin' not found"
}

@test "fails when not in a git repository" {
    cd /tmp || return 1
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "Not a git repository"
}

@test "fails when nonexistent remote is specified" {
    cd "$TEST_REPO" || return 1
    git remote add origin "https://github.com/user/repo.git"
    run bash "$SCRIPT_UNDER_TEST" nonexistent
    assert_failure
    assert_output --partial "Remote 'nonexistent' not found"
}
