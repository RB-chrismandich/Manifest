#!/usr/bin/env bats
# Tests for configs/claude/scripts/git_ops.sh
# Subcommand routing, unknown subcommand handling, platform detection integration

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../configs/claude/scripts/git_ops.sh"

setup() {
    # Create a temporary directory for each test
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_REPO=$(mktemp -d "$BATS_TMPDIR/git_ops_test.XXXXXX")

    # Initialize a git repo with a GitHub remote
    git init "$TEST_REPO" > /dev/null 2>&1
    cd "$TEST_REPO" || return 1
    git remote add origin "https://github.com/user/repo.git"

    # Create mock bin directory for stub commands
    MOCK_BIN=$(mktemp -d "$BATS_TMPDIR/git_ops_mockbin.XXXXXX")
    export PATH="$MOCK_BIN:$PATH"

    # Clear env overrides
    unset MANIFEST_GIT_PLATFORM
    unset MANIFEST_GIT_REMOTE
}

teardown() {
    if [[ -n "$TEST_REPO" && -d "$TEST_REPO" ]]; then
        rm -rf "$TEST_REPO"
    fi
    if [[ -n "$MOCK_BIN" && -d "$MOCK_BIN" ]]; then
        rm -rf "$MOCK_BIN"
    fi
}

# Helper: create a stub command that records its invocation
create_stub() {
    local cmd_name="$1"
    local exit_code="${2:-0}"
    cat > "$MOCK_BIN/$cmd_name" << STUB
#!/usr/bin/env bash
echo "STUB:$cmd_name:\$*"
exit $exit_code
STUB
    chmod +x "$MOCK_BIN/$cmd_name"
}

# Build a curated bin dir containing only the tools the script needs (bash,
# git, dirname) and NOT gh/glab. Needed because CI runners (GitHub Actions)
# ship gh in /usr/bin, so a broad PATH like /usr/bin:/bin can't simulate its
# absence. Echoes the dir path; caller is responsible for cleanup.
make_clean_bin() {
    local clean_bin
    clean_bin=$(mktemp -d "$BATS_TMPDIR/git_ops_clean.XXXXXX")
    ln -s "$(command -v bash)" "$clean_bin/bash"
    ln -s "$(command -v git)" "$clean_bin/git"
    ln -s "$(command -v dirname)" "$clean_bin/dirname"
    echo "$clean_bin"
}

# --- No arguments tests ---

@test "shows usage when no subcommand provided" {
    cd "$TEST_REPO" || return 1
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "Usage: git_ops.sh <subcommand>"
}

# --- GitHub routing tests ---

@test "routes issue-view to gh issue view" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-view 42
    assert_success
    assert_output --partial "STUB:gh:issue view 42"
}

@test "routes issue-list to gh issue list" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-list --state open
    assert_success
    assert_output --partial "STUB:gh:issue list --state open"
}

@test "routes issue-create to gh issue create" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-create --title "Bug"
    assert_success
    assert_output --partial "STUB:gh:issue create --title Bug"
}

@test "routes issue-comment to gh issue comment" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-comment 10 --body "Hello"
    assert_success
    assert_output --partial "STUB:gh:issue comment 10 --body Hello"
}

@test "routes issue-close to gh issue close" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-close 7
    assert_success
    assert_output --partial "STUB:gh:issue close 7"
}

@test "routes issue-edit to gh issue edit" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-edit 5 --title "Updated"
    assert_success
    assert_output --partial "STUB:gh:issue edit 5 --title Updated"
}

@test "routes pr-create to gh pr create" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-create --title "Fix" --body "desc"
    assert_success
    assert_output --partial "STUB:gh:pr create --title Fix --body desc"
}

@test "routes pr-view to gh pr view" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-view 99
    assert_success
    assert_output --partial "STUB:gh:pr view 99"
}

@test "routes pr-list to gh pr list" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-list
    assert_success
    assert_output --partial "STUB:gh:pr list"
}

@test "routes pr-edit to gh pr edit (append body on GitHub)" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-edit 99 --body "Closes #17"
    assert_success
    assert_output --partial "STUB:gh:pr edit 99 --body Closes #17"
}

@test "routes label-create to gh label create" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" label-create "bug" --color "FF0000"
    assert_success
    assert_output --partial "STUB:gh:label create bug --color FF0000"
}

@test "routes label-list to gh label list" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" label-list
    assert_success
    assert_output --partial "STUB:gh:label list"
}

# --- GitLab routing tests ---

@test "routes issue-view to glab issue view on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" issue-view 42
    assert_success
    assert_output --partial "STUB:glab:issue view 42"
}

@test "routes pr-create to glab mr create on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-create --title "Fix"
    assert_success
    assert_output --partial "STUB:glab:mr create --title Fix"
}

@test "routes pr-edit to glab mr update (--body → --description) on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-edit 99 --body "Closes #17"
    assert_success
    assert_output --partial "STUB:glab:mr update 99 --description Closes #17"
}

@test "routes issue-comment to glab issue note on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" issue-comment 10 --body "Hello"
    assert_success
    assert_output --partial "STUB:glab:issue note 10 --body Hello"
}

@test "routes issue-edit to glab issue update on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" issue-edit 5 --title "Updated"
    assert_success
    assert_output --partial "STUB:glab:issue update 5 --title Updated"
}

@test "issue-edit --add-label/--remove-label translate to glab --label/--unlabel" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" issue-edit 17 --add-label in-progress --remove-label planned
    assert_success
    assert_output --partial "STUB:glab:issue update 17 --label in-progress --unlabel planned"
}

# --- Unknown subcommand tests ---

@test "fails on unknown subcommand for GitHub" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" unknown-cmd
    assert_failure
    assert_output --partial "Unknown subcommand: unknown-cmd"
}

@test "fails on unknown subcommand for GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" unknown-cmd
    assert_failure
    assert_output --partial "Unknown subcommand: unknown-cmd"
}

# --- Plain git remote tests ---

@test "warns when using issue commands on plain git remote" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "ssh://git@myserver.local/repo.git"
    run bash "$SCRIPT_UNDER_TEST" issue-view 1
    assert_failure
    assert_output --partial "No issue tracker detected"
}

@test "warns when using pr commands on plain git remote" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "ssh://git@myserver.local/repo.git"
    run bash "$SCRIPT_UNDER_TEST" pr-create --title "Fix"
    assert_failure
    assert_output --partial "No issue tracker detected"
}

# --- Missing CLI tool tests ---

@test "fails when gh CLI is not installed for GitHub remote" {
    cd "$TEST_REPO" || return 1
    local clean_bin
    clean_bin=$(make_clean_bin)
    run env PATH="$MOCK_BIN:$clean_bin" bash "$SCRIPT_UNDER_TEST" issue-view 1
    rm -rf "$clean_bin"
    assert_failure
    assert_output --partial "CLI not found"
}

@test "fails when glab CLI is not installed for GitLab remote" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    local clean_bin
    clean_bin=$(make_clean_bin)
    run env PATH="$MOCK_BIN:$clean_bin" bash "$SCRIPT_UNDER_TEST" issue-view 1
    rm -rf "$clean_bin"
    assert_failure
    assert_output --partial "CLI not found"
}

# --- Platform override integration ---

@test "MANIFEST_GIT_PLATFORM overrides remote detection in git_ops" {
    cd "$TEST_REPO" || return 1
    # Remote is GitHub, but we force GitLab
    export MANIFEST_GIT_PLATFORM="gitlab"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" issue-view 42
    assert_success
    assert_output --partial "STUB:glab:issue view 42"
}

# --- issue-comment body normalization (issue #475) ---

@test "issue-comment: positional body is normalized to --body (github)" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-comment 42 "hello world"
    assert_success
    assert_output --partial "STUB:gh:issue comment 42 --body hello world"
}

@test "issue-comment: flag-style invocation passes through unchanged" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" issue-comment 42 --body "hi"
    assert_success
    assert_output --partial "STUB:gh:issue comment 42 --body hi"
}

@test "issue-comment: positional body is normalized to --message (gitlab)" {
    cd "$TEST_REPO" || return 1
    create_stub "glab"
    export MANIFEST_GIT_PLATFORM=gitlab
    run bash "$SCRIPT_UNDER_TEST" issue-comment 42 "hello world"
    assert_success
    assert_output --partial "STUB:glab:issue note 42 --message hello world"
}

# --- pr-close / pr-comment / pr-comments (Task 13) ---

@test "routes pr-close to gh pr close" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-close 42
    assert_success
    assert_output --partial "STUB:gh:pr close 42"
}

@test "routes pr-comment to gh pr comment" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-comment 42 --body "Hello"
    assert_success
    assert_output --partial "STUB:gh:pr comment 42 --body Hello"
}

@test "pr-comment: positional body is normalized to --body (github)" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-comment 42 "hello world"
    assert_success
    assert_output --partial "STUB:gh:pr comment 42 --body hello world"
}

@test "routes pr-comments to gh api repos/{owner}/{repo}/pulls/N/comments" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-comments 42
    assert_success
    assert_output --partial "STUB:gh:api repos/{owner}/{repo}/pulls/42/comments --jq"
}

@test "routes pr-close to glab mr close on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-close 42
    assert_success
    assert_output --partial "STUB:glab:mr close 42"
}

@test "routes pr-comment to glab mr note on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-comment 42 --message "Hello"
    assert_success
    assert_output --partial "STUB:glab:mr note 42 --message Hello"
}

@test "pr-comment: positional body is normalized to --message (gitlab)" {
    cd "$TEST_REPO" || return 1
    create_stub "glab"
    export MANIFEST_GIT_PLATFORM=gitlab
    run bash "$SCRIPT_UNDER_TEST" pr-comment 42 "hello world"
    assert_success
    assert_output --partial "STUB:glab:mr note 42 --message hello world"
}

@test "routes pr-comments to glab api projects/:id/merge_requests/N/notes on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-comments 42
    assert_success
    assert_output --partial "STUB:glab:api projects/:id/merge_requests/42/notes?sort=asc --jq"
}

# --- pr-reopen / pr-update-branch / repo-admin-check / branch-protection / commit-checks (Task 15) ---

@test "pr-close --comment translates to glab mr note + mr close on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-close 42 --comment "Closing as stale"
    assert_success
    assert_output --partial "STUB:glab:mr note 42 --message Closing as stale"
    assert_output --partial "STUB:glab:mr close 42"
}

@test "routes pr-reopen to gh pr reopen" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-reopen 42
    assert_success
    assert_output --partial "STUB:gh:pr reopen 42"
}

@test "routes pr-reopen to glab mr reopen on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-reopen 42
    assert_success
    assert_output --partial "STUB:glab:mr reopen 42"
}

@test "routes pr-update-branch to gh pr update-branch" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" pr-update-branch 42
    assert_success
    assert_output --partial "STUB:gh:pr update-branch 42"
}

@test "routes pr-update-branch to glab merge_requests rebase on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" pr-update-branch 42
    assert_success
    assert_output --partial "STUB:glab:api projects/:id/merge_requests/42/rebase -X PUT"
}

@test "routes repo-admin-check to gh api repos/{owner}/{repo}" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" repo-admin-check
    assert_success
    assert_output --partial "STUB:gh:api repos/{owner}/{repo} -q .permissions.admin"
}

@test "routes repo-admin-check to glab api projects/:id on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" repo-admin-check
    assert_success
    assert_output --partial "STUB:glab:api projects/:id --jq"
}

@test "routes branch-protection to gh api branches/main/protection" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" branch-protection
    assert_success
    assert_output --partial "STUB:gh:api repos/{owner}/{repo}/branches/main/protection -q"
}

@test "branch-protection has no GitLab equivalent (github-only, fails loud)" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" branch-protection
    assert_failure
    assert_output --partial "no GitLab equivalent"
}

@test "routes commit-checks to gh api commits/SHA/check-runs" {
    cd "$TEST_REPO" || return 1
    create_stub "gh"
    run bash "$SCRIPT_UNDER_TEST" commit-checks abc123
    assert_success
    assert_output --partial "STUB:gh:api repos/{owner}/{repo}/commits/abc123/check-runs -q"
}

@test "routes commit-checks to glab api repository/commits/SHA/statuses on GitLab" {
    cd "$TEST_REPO" || return 1
    git remote set-url origin "https://gitlab.com/user/repo.git"
    create_stub "glab"
    run bash "$SCRIPT_UNDER_TEST" commit-checks abc123
    assert_success
    assert_output --partial "STUB:glab:api projects/:id/repository/commits/abc123/statuses --jq"
}
