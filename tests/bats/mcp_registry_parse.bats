#!/usr/bin/env bats
# Tests for bootstrap/lib/mcp.sh parse_mcp_registry.
#
# This function had NO coverage, which is how a real defect stayed invisible:
# the awk fallback used to identify server keys by excluding a deny-list of
# known field names, so adding `shipped:` to the registry silently replaced
# context7 with a server called "shipped: true" — dropping the only shipped
# server on precisely the machines that cannot use the python path.
#
# The parser now keys on indentation instead. These tests pin the two things
# that matter: the fallback agrees with the python path on the real registry,
# and an unrecognised field can never be mistaken for a server.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

# `run -127` (exit-code assertion) needs bats >= 1.5.0.
bats_require_minimum_version 1.5.0

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/mcp_registry_parse.XXXXXX")

    # Stub print helpers (defined in common.sh; mcp.sh calls them)
    print_step()    { :; }
    print_success() { :; }
    print_info()    { :; }
    print_warning() { :; }
    print_error()   { :; }
    print_header()  { :; }
    command_exists() { command -v "$1" > /dev/null 2>&1; }

    # parse_mcp_registry reads "$SCRIPT_DIR/configs/claude/config/mcp_servers.yml"
    SCRIPT_DIR="$SANDBOX"
    REGISTRY="$SANDBOX/configs/claude/config/mcp_servers.yml"
    mkdir -p "$(dirname "$REGISTRY")"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/mcp.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Force the awk fallback by shadowing python3 with an exit-127 stub. Emptying
# PATH does not work: on ubuntu-latest /bin is a symlink to /usr/bin, so a
# "minimal PATH" still resolves the real interpreter.
force_awk_fallback() {
    mkdir -p "$SANDBOX/bin"
    printf '#!/bin/sh\nexit 127\n' > "$SANDBOX/bin/python3"
    chmod +x "$SANDBOX/bin/python3"
    PATH="$SANDBOX/bin:$PATH"
}

# Render the parsed arrays as name|url|transport|purpose lines for comparison.
dump_parsed() {
    local i
    for i in "${!MCP_SERVER_NAMES[@]}"; do
        echo "${MCP_SERVER_NAMES[$i]}|${MCP_SERVER_URLS[$i]}|${MCP_SERVER_TRANSPORTS[$i]}|${MCP_SERVER_PURPOSES[$i]}"
    done
}

# ── Parity: the fallback must not disagree with python ──────────────────────

@test "awk fallback and python path agree on the real registry" {
    cp "$REPO_ROOT/configs/claude/config/mcp_servers.yml" "$REGISTRY"

    parse_mcp_registry
    local via_python
    via_python=$(dump_parsed)

    # Confirm the stub is in front: without this the "fallback" test would
    # silently re-run the python path and assert nothing.
    force_awk_fallback
    run -127 python3 --version

    parse_mcp_registry
    local via_awk
    via_awk=$(dump_parsed)

    [ -n "$via_python" ]
    assert_equal "$via_awk" "$via_python"
}

@test "real registry parses to every catalog server, shipped one included" {
    cp "$REPO_ROOT/configs/claude/config/mcp_servers.yml" "$REGISTRY"
    force_awk_fallback

    parse_mcp_registry

    # The catalog is what --install-mcp offers; it must stay whole even though
    # only context7 is registered by default.
    [ "${#MCP_SERVER_NAMES[@]}" -eq 9 ]
    run dump_parsed
    assert_line --partial "context7|https://mcp.context7.com/mcp/oauth|http|"
    refute_output --partial "shipped"
}

# ── The regression that motivated the rewrite ───────────────────────────────

@test "an unrecognised field is not mistaken for a server" {
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  alpha:
    url: "https://example.com/alpha"
    transport: "http"
    shipped: true
    some_future_field: whatever
    purpose: "Alpha purpose"
EOF
    force_awk_fallback

    parse_mcp_registry

    [ "${#MCP_SERVER_NAMES[@]}" -eq 1 ]
    assert_equal "${MCP_SERVER_NAMES[0]}" "alpha"
    assert_equal "${MCP_SERVER_URLS[0]}" "https://example.com/alpha"
    assert_equal "${MCP_SERVER_PURPOSES[0]}" "Alpha purpose"
}

@test "a field named like a server does not shadow the entry it belongs to" {
    # The exact old failure: `shipped: true` between the url and the purpose
    # replaced the server name, so context7 vanished and "shipped: true"
    # appeared in its place.
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  first:
    url: "https://example.com/first"
    purpose: "First"
  second:
    url: "https://example.com/second"
    shipped: true
    purpose: "Second"
  third:
    url: "https://example.com/third"
    purpose: "Third"
EOF
    force_awk_fallback

    parse_mcp_registry

    [ "${#MCP_SERVER_NAMES[@]}" -eq 3 ]
    assert_equal "${MCP_SERVER_NAMES[*]}" "first second third"
}

# ── Structural robustness the old parser lacked ─────────────────────────────

@test "field order is free (purpose is no longer the record terminator)" {
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  ordered:
    url: "https://example.com/ordered"
    purpose: "Purpose first"
    transport: "sse"
    shipped: true
EOF
    force_awk_fallback

    parse_mcp_registry

    [ "${#MCP_SERVER_NAMES[@]}" -eq 1 ]
    assert_equal "${MCP_SERVER_TRANSPORTS[0]}" "sse"
    assert_equal "${MCP_SERVER_PURPOSES[0]}" "Purpose first"
}

@test "a server with no purpose is still emitted" {
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  bare:
    url: "https://example.com/bare"
    transport: "http"
EOF
    force_awk_fallback

    parse_mcp_registry

    [ "${#MCP_SERVER_NAMES[@]}" -eq 1 ]
    assert_equal "${MCP_SERVER_NAMES[0]}" "bare"
    assert_equal "${MCP_SERVER_PURPOSES[0]}" ""
}

@test "an entry without a url is skipped, not emitted with an empty url" {
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  has-url:
    url: "https://example.com/has-url"
    purpose: "Kept"
  no-url:
    transport: "stdio"
    purpose: "Dropped"
EOF
    force_awk_fallback

    parse_mcp_registry

    [ "${#MCP_SERVER_NAMES[@]}" -eq 1 ]
    assert_equal "${MCP_SERVER_NAMES[0]}" "has-url"
}

@test "section comments between servers are not parsed as entries" {
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  # ── Core ─────────────────────────────────────────────
  alpha:
    url: "https://example.com/alpha"
    purpose: "Alpha"

  # ── Knowledge ────────────────────────────────────────
  beta:
    url: "https://example.com/beta"
    purpose: "Beta"
EOF
    force_awk_fallback

    parse_mcp_registry

    [ "${#MCP_SERVER_NAMES[@]}" -eq 2 ]
    assert_equal "${MCP_SERVER_NAMES[*]}" "alpha beta"
}

@test "a missing registry file fails instead of reporting zero servers" {
    force_awk_fallback

    run parse_mcp_registry
    [ "$status" -ne 0 ]
}
