#!/usr/bin/env bats
# merge_claude_mcp_servers(): user-added MCP servers in the live
# ~/.claude/settings.local.json must survive a bootstrap redeploy. The repo
# ships its own settings.local.json (with default mcpServers); the destructive
# copy in deploy_configs would otherwise drop any server the user added.
# User entries win on key conflicts — "keep them intact".

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    TMPDIR_T="$(mktemp -d)"
    PRESERVED="$TMPDIR_T/preserved.json"  # snapshot of live settings.local.json
    TGT="$TMPDIR_T/tgt.json"              # freshly deployed repo copy

    command_exists() { command -v "$1" > /dev/null 2>&1; }
    print_info() { echo "INFO: $*"; }
    print_success() { echo "OK: $*"; }
    print_warning() { echo "WARN: $*"; }
    export -f command_exists print_info print_success print_warning 2> /dev/null || true

    # shellcheck disable=SC1091
    source "$REPO_ROOT/bootstrap/lib/deploy.sh" 2> /dev/null || true

    # Repo-shipped default (what the deploy just copied into place)
    cat > "$TGT" <<'EOF'
{
  "mcpServers": {
    "sentry": { "url": "https://mcp.sentry.dev/mcp" },
    "linear": { "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.linear.app/mcp"] }
  }
}
EOF
}

teardown() {
    rm -rf "$TMPDIR_T"
}

@test "user-added MCP server is restored into the deployed settings.local.json" {
    cat > "$PRESERVED" <<'EOF'
{
  "mcpServers": {
    "sentry": { "url": "https://mcp.sentry.dev/mcp" },
    "linear": { "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.linear.app/mcp"] },
    "my-private": { "url": "https://mcp.internal.example/mcp" }
  }
}
EOF
    run merge_claude_mcp_servers "$PRESERVED" "$TGT"
    assert_success
    assert_output --partial "Preserved user MCP servers"

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['mcpServers']['my-private']['url'] == 'https://mcp.internal.example/mcp'
assert 'sentry' in d['mcpServers'] and 'linear' in d['mcpServers']
print('user-server-preserved')"
    assert_output --partial "user-server-preserved"
}

@test "user customization wins on key conflict (kept intact)" {
    cat > "$PRESERVED" <<'EOF'
{
  "mcpServers": {
    "sentry": { "url": "https://sentry.internal.example/custom" }
  }
}
EOF
    run merge_claude_mcp_servers "$PRESERVED" "$TGT"
    assert_success

    run python3 -c "
import json
d = json.load(open('$TGT'))
assert d['mcpServers']['sentry']['url'] == 'https://sentry.internal.example/custom', d['mcpServers']['sentry']
print('user-wins')"
    assert_output --partial "user-wins"
}

@test "no user-added servers (live == repo defaults) is a clean no-op" {
    cat > "$PRESERVED" <<'EOF'
{
  "mcpServers": {
    "sentry": { "url": "https://mcp.sentry.dev/mcp" },
    "linear": { "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.linear.app/mcp"] }
  }
}
EOF
    local before
    before=$(cat "$TGT")
    run merge_claude_mcp_servers "$PRESERVED" "$TGT"
    assert_success
    assert_output --partial "No user-added MCP servers"
    assert_equal "$(cat "$TGT")" "$before"
}

@test "missing preserved snapshot is a no-op (fresh install)" {
    run merge_claude_mcp_servers "" "$TGT"
    assert_success
}

@test "malformed preserved snapshot fails open (deployed file untouched, warning)" {
    echo '{ not json' > "$PRESERVED"
    local before
    before=$(cat "$TGT")
    run merge_claude_mcp_servers "$PRESERVED" "$TGT"
    assert_success
    assert_output --partial "WARN"
    assert_equal "$(cat "$TGT")" "$before"
}

@test "preserved snapshot with no mcpServers key is a clean no-op" {
    echo '{ "permissions": { "allow": [] } }' > "$PRESERVED"
    local before
    before=$(cat "$TGT")
    run merge_claude_mcp_servers "$PRESERVED" "$TGT"
    assert_success
    assert_equal "$(cat "$TGT")" "$before"
}
