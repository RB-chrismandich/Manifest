#!/usr/bin/env bats
# MCP server registration: mcp_plan.py + install_claude_mcp_servers.
#
# REGRESSION GUARD. The first version embedded the plan logic as a quoted
# heredoc feeding a process substitution inside deploy.sh. Extracted and called
# directly it worked perfectly — 4 servers added — so a unit test that sourced
# only the function passed. But once bootstrap SOURCED the whole deploy.sh, the
# heredoc body stopped being treated as quoted, bash brace-expanded
# `{**a, **b}` inside the Python, the parser died with a SyntaxError, and the
# caller saw zero rows and reported "MCP servers already registered - preserved"
# — a silent no-op that looked like success.
#
# So the test below sources deploy.sh WHOLE, the way bootstrap does, rather than
# sed-extracting the function. A test that only exercises the extracted function
# cannot see this class of bug.

bats_require_minimum_version 1.5.0

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/mcp_reg.XXXXXX")"
    PLAN="$REPO_ROOT/configs/claude/scripts/mcp_plan.py"
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude" "$SANDBOX/bin"
    export TARGET_DIR="$HOME/.claude"
    export SCRIPT_DIR="$REPO_ROOT"
    export MCP_STUB_LOG="$SANDBOX/adds.log"
    : > "$MCP_STUB_LOG"
    cat > "$SANDBOX/bin/claude" << 'STUB'
#!/usr/bin/env bash
[[ "$1 $2" == "mcp add" ]] && { printf '%s\n' "$*" >> "$MCP_STUB_LOG"; exit 0; }
exit 0
STUB
    chmod +x "$SANDBOX/bin/claude"
    # A FIXTURE, not the shipped list: these tests verify the mechanism (both
    # transports, idempotency, rescue, guards). Coupling them to the real
    # server list means pruning a server you no longer use breaks the suite and
    # silently drops http-transport coverage.
    SRC="$REPO_ROOT/tests/bats/fixtures/mcp/servers.json"
    REPO_SERVERS="$REPO_ROOT/configs/claude/config/mcp_user_servers.json"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Source deploy.sh WHOLE — this is the point of the regression guard.
run_install() {
    PATH="$SANDBOX/bin:$PATH" bash -c '
        set -o pipefail
        # common.sh reads colour vars at source time; seed them before sourcing.
        GREEN="" CYAN="" NC="" BLUE="" YELLOW="" RED="" BOLD=""
        print_info(){ echo "INFO: $*"; }
        print_success(){ echo "OK: $*"; }
        print_warning(){ echo "WARN: $*"; }
        print_step(){ :; }; print_header(){ :; }; print_error(){ echo "ERR: $*"; }
        source "$1/bootstrap/lib/common.sh"
        source "$1/bootstrap/lib/deploy.sh"
        install_claude_mcp_servers "$2" "${3:-}"
    ' _ "$REPO_ROOT" "$SRC" "${1:-}" 2>&1
}

@test "mcp_plan.py --help exits 0 and prints Usage" {
    run python3 "$PLAN" --help
    assert_success
    assert_output --partial "Usage"
}

@test "plan emits a row per repo server with the right transport" {
    run env MCP_SRC="$SRC" MCP_HOME="$SANDBOX/absent.json" python3 "$PLAN"
    assert_success
    assert_output --partial "fixture-http	http	https://mcp.example.test/mcp"
    assert_output --partial "fixture-stdio	stdio	npx -y mcp-remote"
}

@test "plan marks an already-registered server present, not to-add" {
    printf '{"mcpServers":{"fixture-http":{"url":"x"}}}' > "$SANDBOX/claude.json"
    run env MCP_SRC="$SRC" MCP_HOME="$SANDBOX/claude.json" python3 "$PLAN"
    assert_success
    assert_output --partial "fixture-http	present"
}

@test "plan rescues a server stranded in the inert settings.local.json" {
    printf '{"mcpServers":{"my-private":{"url":"https://mcp.internal/mcp"}}}' > "$SANDBOX/legacy.json"
    run env MCP_SRC="$SRC" MCP_LEGACY="$SANDBOX/legacy.json" MCP_HOME="$SANDBOX/absent.json" python3 "$PLAN"
    assert_success
    assert_output --partial "my-private	http	https://mcp.internal/mcp"
}

@test "plan degrades to no rows on unreadable input, never an error" {
    run env MCP_SRC="$SANDBOX/nope.json" python3 "$PLAN"
    assert_success
    assert_output ""
}

@test "REGRESSION: registration works when deploy.sh is SOURCED whole" {
    # The bug this file exists for: standalone the function added 4 servers,
    # sourced-whole it silently added 0 and claimed success.
    run run_install
    assert_success
    assert_output --partial "2 added"
    refute_output --partial "SyntaxError"
    refute_output --partial "ambiguous redirect"
    run cat "$MCP_STUB_LOG"
    assert_output --partial "--transport http fixture-http"
    assert_output --partial "fixture-stdio -- npx -y mcp-remote"
}

@test "REGRESSION: no server is added twice on a second run" {
    printf '{"mcpServers":{"fixture-http":{"url":"x"},"fixture-stdio":{"command":"npx"}}}' \
        > "$HOME/.claude.json"
    run run_install
    assert_success
    assert_output --partial "already registered"
    run cat "$MCP_STUB_LOG"
    assert_output ""
}

@test "refuses to touch a real HOME when the deploy target is outside it" {
    # install_claude_mcp_servers is the one deploy step that writes outside
    # $TARGET_DIR; without this guard a sandboxed test edits the developer's
    # own MCP config (observed).
    run env TARGET_DIR="$SANDBOX/elsewhere/.claude" bash -c '
        GREEN="" CYAN="" NC="" BLUE="" YELLOW="" RED="" BOLD=""
        print_info(){ echo "INFO: $*"; }
        print_success(){ echo "OK: $*"; }
        print_warning(){ echo "WARN: $*"; }
        print_step(){ :; }; print_header(){ :; }; print_error(){ :; }
        source "$1/bootstrap/lib/common.sh"
        source "$1/bootstrap/lib/deploy.sh"
        install_claude_mcp_servers "$2"
    ' _ "$REPO_ROOT" "$SRC"
    assert_success
    assert_output --partial "skipped"
    run cat "$MCP_STUB_LOG"
    assert_output ""
}

@test "the shipped MCP list is valid and parses to a plan" {
    # Decoupled from the fixture above: this is the only test that reads the
    # real file, so pruning a server is a one-line config change, not a test edit.
    run env MCP_SRC="$REPO_SERVERS" MCP_HOME="$SANDBOX/absent.json" python3 "$PLAN"
    assert_success
    run python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(type(d).__name__, len(d))" "$REPO_SERVERS"
    assert_success
    assert_output --partial "dict"
}
