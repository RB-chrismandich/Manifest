#!/bin/bash

# Mock environment
TARGET_DIR=$(mktemp -d)
CURSOR_TARGET_DIR="$TARGET_DIR/cursor"
export TARGET_DIR
export CURSOR_TARGET_DIR
export BOLD=""
export NC=""
export CYAN=""
export GREEN=""
export YELLOW=""
export RED=""
export BLUE=""
export SCRIPT_DIR="$PWD"

# Mock common.sh functions
print_step() { echo "STEP: $1"; }
print_success() { echo "SUCCESS: $1"; }
print_warning() { echo "WARNING: $1"; }
print_error() { echo "ERROR: $1"; }
print_info() { echo "INFO: $1"; }
prompt_yes_no() { echo "YESNO: $1"; return 0; } # Assume Yes
command_exists() { command -v "$1" &> /dev/null; }

# Mock variables for mcp.sh
MCP_SELECTED_INDICES=(0)
MCP_SERVER_NAMES=("test_server")
MCP_SERVER_URLS=("http://test.url")
MCP_SERVER_TRANSPORTS=("sse")
MCP_SERVER_PURPOSES=("testing")

# Source libraries
# We need to temporarily disable shellcheck for sourcing
# shellcheck source=/dev/null
source bootstrap/lib/auth.sh
# shellcheck source=/dev/null
source bootstrap/lib/mcp.sh

FAILURES=0

test_gemini_auth_new() {
    echo "Testing setup_gemini_auth (new file)..."
    # Input: 2 (API Key), then the key
    (echo "2"; echo "my-secret-key") | setup_gemini_auth > /dev/null

    ENV_FILE="$TARGET_DIR/gemini_env.sh"
    if [[ -f "$ENV_FILE" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            PERMS=$(stat -f "%OLp" "$ENV_FILE")
        else
            PERMS=$(stat -c "%a" "$ENV_FILE")
        fi

        echo "Permissions: $PERMS"
        if [[ "$PERMS" != "600" ]]; then
            echo "FAIL: Permissions are not 600"
            FAILURES=$((FAILURES + 1))
        else
            echo "PASS: Permissions are 600"
        fi

        CONTENT=$(cat "$ENV_FILE")
        if [[ "$CONTENT" == "export GEMINI_API_KEY='my-secret-key'" ]]; then
             echo "PASS: Content matches"
        else
             echo "FAIL: Content mismatch: $CONTENT"
             FAILURES=$((FAILURES + 1))
        fi
    else
        echo "FAIL: File not created"
        FAILURES=$((FAILURES + 1))
    fi
}

test_gemini_auth_existing() {
    echo "Testing setup_gemini_auth (existing insecure file)..."
    ENV_FILE="$TARGET_DIR/gemini_env.sh"
    touch "$ENV_FILE"
    chmod 644 "$ENV_FILE"
    echo "old_content" > "$ENV_FILE"

    # Input: 2 (API Key), then the key
    (echo "2"; echo "new-secret-key") | setup_gemini_auth > /dev/null

    if [[ -f "$ENV_FILE" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            PERMS=$(stat -f "%OLp" "$ENV_FILE")
        else
            PERMS=$(stat -c "%a" "$ENV_FILE")
        fi

        echo "Permissions: $PERMS"
        if [[ "$PERMS" != "600" ]]; then
            echo "FAIL: Permissions are not 600 (was likely 644)"
            FAILURES=$((FAILURES + 1))
        else
            echo "PASS: Permissions are 600"
        fi

        CONTENT=$(cat "$ENV_FILE")
        if [[ "$CONTENT" == "export GEMINI_API_KEY='new-secret-key'" ]]; then
             echo "PASS: Content matches"
        else
             echo "FAIL: Content mismatch: $CONTENT"
             FAILURES=$((FAILURES + 1))
        fi
    else
        echo "FAIL: File not created"
        FAILURES=$((FAILURES + 1))
    fi
}

test_cursor_mcp_new() {
    echo "Testing configure_cursor_mcp_config (new file)..."
    # Ensure dir is clean
    rm -rf "$CURSOR_TARGET_DIR"
    configure_cursor_mcp_config > /dev/null

    MCP_FILE="$CURSOR_TARGET_DIR/mcp.json"
    if [[ -f "$MCP_FILE" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            PERMS=$(stat -f "%OLp" "$MCP_FILE")
        else
            PERMS=$(stat -c "%a" "$MCP_FILE")
        fi

        echo "Permissions: $PERMS"
        if [[ "$PERMS" != "600" ]]; then
            echo "FAIL: Permissions are not 600"
            FAILURES=$((FAILURES + 1))
        else
            echo "PASS: Permissions are 600"
        fi

        if grep -q "test_server" "$MCP_FILE"; then
             echo "PASS: Content contains server name"
        else
             echo "FAIL: Content missing server name"
             cat "$MCP_FILE"
             FAILURES=$((FAILURES + 1))
        fi
    else
        echo "FAIL: File not created"
        FAILURES=$((FAILURES + 1))
    fi
}

test_cursor_mcp_existing() {
    echo "Testing configure_cursor_mcp_config (existing insecure file)..."
    mkdir -p "$CURSOR_TARGET_DIR"
    MCP_FILE="$CURSOR_TARGET_DIR/mcp.json"
    touch "$MCP_FILE"
    chmod 644 "$MCP_FILE"
    echo "{}" > "$MCP_FILE"

    # Mock is_cursor_mcp_current to return false so it overwrites
    # We rely on the fact that is_cursor_mcp_current checks for content, and we put empty content
    # But wait, our mock in common.sh/mcp.sh works.
    # is_cursor_mcp_current uses jq or grep. If file is empty or {}, it fails the check, so it proceeds to overwrite.

    configure_cursor_mcp_config > /dev/null

    if [[ -f "$MCP_FILE" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            PERMS=$(stat -f "%OLp" "$MCP_FILE")
        else
            PERMS=$(stat -c "%a" "$MCP_FILE")
        fi

        echo "Permissions: $PERMS"
        if [[ "$PERMS" != "600" ]]; then
            echo "FAIL: Permissions are not 600 (was likely 644)"
            FAILURES=$((FAILURES + 1))
        else
            echo "PASS: Permissions are 600"
        fi

        if grep -q "test_server" "$MCP_FILE"; then
             echo "PASS: Content contains server name"
        else
             echo "FAIL: Content missing server name"
             cat "$MCP_FILE"
             FAILURES=$((FAILURES + 1))
        fi
    else
        echo "FAIL: File not created"
        FAILURES=$((FAILURES + 1))
    fi
}

# Run tests
test_gemini_auth_new
test_gemini_auth_existing
test_cursor_mcp_new
test_cursor_mcp_existing

# Cleanup
rm -rf "$TARGET_DIR"

if [[ $FAILURES -eq 0 ]]; then
    echo "All tests passed"
    exit 0
else
    echo "$FAILURES tests failed"
    exit 1
fi
