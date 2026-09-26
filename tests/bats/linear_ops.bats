#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/linear_ops.sh
# Authentication (LINEAR_API_KEY only), subcommand routing, error handling

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/linear_ops.sh"

setup() {
    # Create a temporary directory for each test
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/linear_ops_test.XXXXXX")

    # Create mock bin directory for stub commands
    MOCK_BIN=$(mktemp -d "$BATS_TMPDIR/linear_ops_mockbin.XXXXXX")
    export PATH="$MOCK_BIN:$PATH"

    # Create mock home directory to isolate config file checks
    MOCK_HOME=$(mktemp -d "$BATS_TMPDIR/linear_ops_home.XXXXXX")
    export HOME="$MOCK_HOME"

    # Create stub for curl (used by graphql_query)
    create_stub "curl"

    # Create stub for jq (used throughout)
    create_stub_jq

    # Forge auth is env-only: LINEAR_API_KEY authenticates every test; tests
    # exercising the no-auth path set LINEAR_API_KEY="" on the run line.
    export LINEAR_API_KEY="test-token"
}

teardown() {
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
    if [[ -n "$MOCK_BIN" && -d "$MOCK_BIN" ]]; then
        rm -rf "$MOCK_BIN"
    fi
    if [[ -n "$MOCK_HOME" && -d "$MOCK_HOME" ]]; then
        rm -rf "$MOCK_HOME"
    fi
}

# Helper: create a stub command that records its invocation
create_stub() {
    local cmd_name="$1"
    local exit_code="${2:-0}"
    local output="${3:-STUB:$cmd_name}"
    cat > "$MOCK_BIN/$cmd_name" << STUB
#!/usr/bin/env bash
echo "$output"
exit $exit_code
STUB
    chmod +x "$MOCK_BIN/$cmd_name"
}

# Helper: create a jq stub that passes through or returns mock data
create_stub_jq() {
    cat > "$MOCK_BIN/jq" << 'STUB'
#!/usr/bin/env bash
# Minimal jq stub: for -Rs, -nc, -r, -c flags just echo input or args
# This is sufficient for argument parsing tests
if [[ "$1" == "-Rs" ]]; then
    cat | sed 's/"/\\"/g; s/^/"/; s/$/"/'
elif [[ "$1" == "-nc" ]]; then
    echo '{}'
elif [[ "$1" == "-r" ]]; then
    cat
elif [[ "$1" == "-c" ]]; then
    cat
elif [[ "$1" == "--arg" || "$1" == "--argjson" ]]; then
    echo '{}'
else
    cat
fi
STUB
    chmod +x "$MOCK_BIN/jq"
}

# --- No arguments tests ---

@test "shows usage when no subcommand provided" {
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "Usage: linear_ops.sh <subcommand>"
}

@test "usage message lists all subcommands" {
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "team-list"
    assert_output --partial "team-states"
    assert_output --partial "issue-list"
    assert_output --partial "issue-view"
    assert_output --partial "issue-create"
    assert_output --partial "issue-update"
    assert_output --partial "issue-comment"
    assert_output --partial "issue-close"
    assert_output --partial "issue-mark-duplicate"
    assert_output --partial "create-sub-issue"
    assert_output --partial "list-cycles"
    assert_output --partial "add-comment"
    assert_output --partial "transition-state"
    assert_output --partial "label-list"
}

# --- Unknown subcommand tests ---

@test "fails on unknown subcommand" {
    run bash "$SCRIPT_UNDER_TEST" unknown-cmd
    assert_failure
    assert_output --partial "Unknown subcommand: unknown-cmd"
}

# --- check_auth tests (issue #312) ---
# Forge auth is LINEAR_API_KEY-only (env); there is no token-file path.

@test "MCP registry entry alone does not authenticate (issue #312)" {
    # The script talks to the API via curl — an MCP registration provides no
    # key, and previously short-circuited auth into an empty Bearer token.
    mkdir -p "$HOME/.claude/config"
    cat > "$HOME/.claude/config/mcp_servers.yml" << EOF
linear:
  url: https://linear.app
EOF

    LINEAR_API_KEY="" run bash "$SCRIPT_UNDER_TEST" team-list
    assert_failure
    assert_output --partial "Linear authentication required"
}

@test "check_auth fails when nothing is configured" {
    LINEAR_API_KEY="" run bash "$SCRIPT_UNDER_TEST" team-list
    assert_failure
    assert_output --partial "Linear authentication required"
}

@test "check_auth succeeds via LINEAR_API_KEY env var" {
    LINEAR_API_KEY="lin_api_env_token" run bash "$SCRIPT_UNDER_TEST" team-list
    refute_output --partial "Linear authentication required"
}

@test "check_auth rejects an empty LINEAR_API_KEY" {
    LINEAR_API_KEY="" run bash "$SCRIPT_UNDER_TEST" team-list
    assert_failure
    assert_output --partial "Linear authentication required"
}

@test "check_auth error message mentions setup options" {
    LINEAR_API_KEY="" run bash "$SCRIPT_UNDER_TEST" team-list
    assert_failure
    assert_output --partial "LINEAR_API_KEY"
    assert_output --partial "linear.app/settings/api"
}

# --- Subcommand routing tests ---
# These tests verify that subcommands are routed correctly.
# Since the script calls graphql_query (which uses curl), we stub curl.
# The actual GraphQL responses are mocked, so we focus on routing.

@test "routes team-list subcommand" {

    run bash "$SCRIPT_UNDER_TEST" team-list
    # Should attempt to call curl (our stub) for GraphQL
    # Won't fail with "Unknown subcommand"
    refute_output --partial "Unknown subcommand"
}

@test "routes team-states subcommand" {

    run bash "$SCRIPT_UNDER_TEST" team-states ENG
    refute_output --partial "Unknown subcommand"
}

@test "routes issue-list subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-list
    refute_output --partial "Unknown subcommand"
}

@test "routes issue-view subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-view ENG-123
    refute_output --partial "Unknown subcommand"
}

@test "routes issue-create subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-create --team ENG --title "New issue"
    refute_output --partial "Unknown subcommand"
}

@test "issue-create fails without --team" {

    run bash "$SCRIPT_UNDER_TEST" issue-create --title "New issue"
    assert_failure
    assert_output --partial "--team"
}

@test "issue-create fails without --title" {

    run bash "$SCRIPT_UNDER_TEST" issue-create --team ENG
    assert_failure
    assert_output --partial "--title required"
}

@test "routes issue-update subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-update ENG-123 --priority 1
    refute_output --partial "Unknown subcommand"
}

@test "routes issue-comment subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-comment ENG-123 --body "Test comment"
    refute_output --partial "Unknown subcommand"
}

@test "routes issue-close subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-close ENG-123
    refute_output --partial "Unknown subcommand"
}

@test "routes issue-mark-duplicate subcommand" {

    run bash "$SCRIPT_UNDER_TEST" issue-mark-duplicate ENG-123 --duplicate-of ENG-100
    refute_output --partial "Unknown subcommand"
}

# --- F-6: identifier argument must be validated before use ---

@test "issue-view requires IDENTIFIER" {
    run bash "$SCRIPT_UNDER_TEST" issue-view
    assert_equal "$status" 1
    assert_output --partial "Usage: issue-view IDENTIFIER"
    refute_output --partial "unbound variable"
}

@test "issue-update requires IDENTIFIER" {
    run bash "$SCRIPT_UNDER_TEST" issue-update
    assert_equal "$status" 1
    assert_output --partial "Usage: issue-update IDENTIFIER"
    refute_output --partial "unbound variable"
}

@test "issue-comment requires IDENTIFIER" {
    run bash "$SCRIPT_UNDER_TEST" issue-comment
    assert_equal "$status" 1
    assert_output --partial "Usage: issue-comment IDENTIFIER"
    refute_output --partial "unbound variable"
}

@test "issue-close requires IDENTIFIER" {
    run bash "$SCRIPT_UNDER_TEST" issue-close
    assert_equal "$status" 1
    assert_output --partial "Usage: issue-close IDENTIFIER"
    refute_output --partial "unbound variable"
}

@test "issue-mark-duplicate requires IDENTIFIER" {
    run bash "$SCRIPT_UNDER_TEST" issue-mark-duplicate
    assert_equal "$status" 1
    assert_output --partial "Usage: issue-mark-duplicate IDENTIFIER"
    refute_output --partial "unbound variable"
}

@test "routes create-sub-issue subcommand" {

    run bash "$SCRIPT_UNDER_TEST" create-sub-issue --parent ENG-123 --title "Sub task"
    refute_output --partial "Unknown subcommand"
}

@test "routes list-cycles subcommand" {

    run bash "$SCRIPT_UNDER_TEST" list-cycles --team ENG
    refute_output --partial "Unknown subcommand"
}

@test "routes add-comment subcommand" {

    run bash "$SCRIPT_UNDER_TEST" add-comment --identifier ENG-123 --body "New comment"
    refute_output --partial "Unknown subcommand"
}

@test "routes transition-state subcommand" {

    run bash "$SCRIPT_UNDER_TEST" transition-state --identifier ENG-123 --state "In Progress"
    refute_output --partial "Unknown subcommand"
}

@test "routes label-list subcommand" {

    run bash "$SCRIPT_UNDER_TEST" label-list
    refute_output --partial "Unknown subcommand"
}

@test "routes label-create subcommand" {

    run bash "$SCRIPT_UNDER_TEST" label-create --name "test-label" --color "FF0000"
    refute_output --partial "Unknown subcommand"
}

@test "label-create fails without --name" {

    run bash "$SCRIPT_UNDER_TEST" label-create --color "FF0000"
    assert_failure
    assert_output --partial "name"
}

@test "label-create fails without --color" {

    run bash "$SCRIPT_UNDER_TEST" label-create --name "test-label"
    assert_failure
    assert_output --partial "--color required"
}

@test "label-create accepts positional name" {

    run bash "$SCRIPT_UNDER_TEST" label-create "my-label" --color "1D76DB"
    refute_output --partial "Unknown subcommand"
}

@test "usage message lists label-create subcommand" {
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    assert_output --partial "label-create"
}

# --- API call construction tests ---

@test "graphql_query passes Authorization header with token" {

    # Replace curl stub with one that records all arguments
    cat > "$MOCK_BIN/curl" << 'STUB'
#!/usr/bin/env bash
echo "CURL_ARGS:$*"
echo '{"data":{"teams":{"nodes":[]}}}'
STUB
    chmod +x "$MOCK_BIN/curl"

    LINEAR_API_KEY="my-secret-token" run bash "$SCRIPT_UNDER_TEST" team-list
    assert_output --partial "Bearer my-secret-token"
}

@test "graphql_query posts to api.linear.app/graphql" {

    cat > "$MOCK_BIN/curl" << 'STUB'
#!/usr/bin/env bash
echo "CURL_ARGS:$*"
echo '{"data":{"teams":{"nodes":[]}}}'
STUB
    chmod +x "$MOCK_BIN/curl"

    run bash "$SCRIPT_UNDER_TEST" team-list
    assert_output --partial "https://api.linear.app/graphql"
}

@test "graphql_query uses POST method" {

    cat > "$MOCK_BIN/curl" << 'STUB'
#!/usr/bin/env bash
echo "CURL_ARGS:$*"
echo '{"data":{"teams":{"nodes":[]}}}'
STUB
    chmod +x "$MOCK_BIN/curl"

    run bash "$SCRIPT_UNDER_TEST" team-list
    assert_output --partial "-X POST"
}

# --- Option parsing tests ---

@test "team-list accepts --json flag" {

    # Stub curl to return valid JSON
    cat > "$MOCK_BIN/curl" << 'STUB'
#!/usr/bin/env bash
echo '{"data":{"teams":{"nodes":[{"id":"1","key":"ENG","name":"Engineering"}]}}}'
STUB
    chmod +x "$MOCK_BIN/curl"

    run bash "$SCRIPT_UNDER_TEST" team-list --json
    refute_output --partial "Unknown option"
}

@test "issue-list accepts --team flag" {

    run bash "$SCRIPT_UNDER_TEST" issue-list --team ENG
    refute_output --partial "Unknown option: --team"
}

@test "issue-list accepts --limit flag" {

    run bash "$SCRIPT_UNDER_TEST" issue-list --limit 10
    refute_output --partial "Unknown option: --limit"
}

@test "issue-list accepts --state flag" {

    run bash "$SCRIPT_UNDER_TEST" issue-list --state started
    refute_output --partial "Unknown option: --state"
}

@test "issue-list accepts --priority flag" {

    run bash "$SCRIPT_UNDER_TEST" issue-list --priority 1
    refute_output --partial "Unknown option: --priority"
}

# --- Error handling for missing required options ---

@test "issue-comment fails without --body" {

    # Stub curl to return issue data for the view call
    cat > "$MOCK_BIN/curl" << 'STUB'
#!/usr/bin/env bash
echo '{"data":{"issue":{"id":"uuid-1","identifier":"ENG-123","team":{"id":"team-1","key":"ENG"},"state":{"name":"Backlog","type":"backlog"}}}}'
STUB
    chmod +x "$MOCK_BIN/curl"

    run bash "$SCRIPT_UNDER_TEST" issue-comment ENG-123
    assert_failure
    assert_output --partial "--body required"
}

@test "issue-mark-duplicate fails without --duplicate-of" {

    run bash "$SCRIPT_UNDER_TEST" issue-mark-duplicate ENG-123
    assert_failure
    assert_output --partial "--duplicate-of required"
}

@test "create-sub-issue fails without --parent" {

    run bash "$SCRIPT_UNDER_TEST" create-sub-issue --title "Test"
    assert_failure
    assert_output --partial "--parent"
}

@test "create-sub-issue fails without --title" {

    run bash "$SCRIPT_UNDER_TEST" create-sub-issue --parent ENG-123
    assert_failure
    assert_output --partial "--title required"
}

@test "list-cycles fails without --team" {

    run bash "$SCRIPT_UNDER_TEST" list-cycles
    assert_failure
    assert_output --partial "--team"
}

@test "add-comment fails without --identifier" {

    run bash "$SCRIPT_UNDER_TEST" add-comment --body "Hello"
    assert_failure
    assert_output --partial "--identifier"
}

@test "add-comment fails without --body" {

    run bash "$SCRIPT_UNDER_TEST" add-comment --identifier ENG-123
    assert_failure
    assert_output --partial "--body required"
}

@test "transition-state fails without --identifier" {

    run bash "$SCRIPT_UNDER_TEST" transition-state --state "In Progress"
    assert_failure
    assert_output --partial "--identifier"
}

@test "transition-state fails without --state" {

    run bash "$SCRIPT_UNDER_TEST" transition-state --identifier ENG-123
    assert_failure
    assert_output --partial "--state"
}
