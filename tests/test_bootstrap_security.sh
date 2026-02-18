#!/bin/bash
set -e

# Mock helpers
print_step() { echo "STEP: $*"; }
print_info() { echo "INFO: $*"; }
print_success() { echo "SUCCESS: $*"; }
print_warning() { echo "WARNING: $*"; }
print_error() { echo "ERROR: $*"; }
print_header() { echo "HEADER: $*"; }
command_exists() { return 0; }
prompt_yes_no() { return 0; }
create_symlink() { echo "SYMLINK: $1 -> $2"; }
link_shared_assets() { echo "LINK_SHARED: $1"; } # Mock this as it's complex

# Create temp directories
TEST_DIR=$(mktemp -d)
CURSOR_TARGET_DIR="$TEST_DIR/cursor"
TARGET_DIR="$TEST_DIR/claude"
GEMINI_TARGET_DIR="$TEST_DIR/gemini"
CODEX_TARGET_DIR="$TEST_DIR/codex"
MANIFEST_OUTPUT_DIR="$TEST_DIR/output"
MANIFEST_STATE_DIR="$TEST_DIR/manifest"
MANIFEST_TMP_DIR="$TEST_DIR/tmp"
SCRIPT_DIR="$TEST_DIR/script_dir"

# Setup mock source files
mkdir -p "$SCRIPT_DIR/configs/cursor/rules"
touch "$SCRIPT_DIR/configs/cursor/rules/test.mdc"
mkdir -p "$SCRIPT_DIR/configs/gemini"
mkdir -p "$SCRIPT_DIR/configs/codex"

# Mock MCP selection variables for mcp.sh
MCP_SELECTED_INDICES=(0)
MCP_SERVER_NAMES=("test-server")
MCP_SERVER_URLS=("https://example.com/mcp")

# Source the libraries
REPO_ROOT="$(pwd)"
source "$REPO_ROOT/bootstrap/lib/common.sh" # For create_symlink if used, but we mocked it
source "$REPO_ROOT/bootstrap/lib/mcp.sh"
source "$REPO_ROOT/bootstrap/lib/auth.sh"
source "$REPO_ROOT/bootstrap/lib/deploy.sh"

echo "--- Testing deploy_cursor_configs ---"
# Set umask to 022
umask 022

# Call the actual function
deploy_cursor_configs

# Check permissions of directory
DIR_PERM=$(stat -c "%a" "$CURSOR_TARGET_DIR")
if [[ "$DIR_PERM" != "700" ]]; then
    echo "FAIL: ~/.cursor permissions are $DIR_PERM, expected 700"
    exit 1
else
    echo "PASS: ~/.cursor permissions are 700"
fi


echo "--- Testing configure_cursor_mcp_config ---"
configure_cursor_mcp_config

MCP_FILE="$CURSOR_TARGET_DIR/mcp.json"
PERM=$(stat -c "%a" "$MCP_FILE")
if [[ "$PERM" != "600" ]]; then
    echo "FAIL: mcp.json permissions are $PERM, expected 600"
    exit 1
else
    echo "PASS: mcp.json permissions are 600"
fi


echo "--- Testing setup_gemini_auth (Option 2: API Key) ---"
export TARGET_DIR="$TARGET_DIR"
# Ensure target dir exists (deploy_configs usually does this)
mkdir -p "$TARGET_DIR"
chmod 700 "$TARGET_DIR"

(echo "2"; echo "my-secret-key") | setup_gemini_auth

ENV_FILE="$TARGET_DIR/gemini_env.sh"
PERM=$(stat -c "%a" "$ENV_FILE")
if [[ "$PERM" != "600" ]]; then
    echo "FAIL: gemini_env.sh permissions are $PERM, expected 600"
    exit 1
else
    echo "PASS: gemini_env.sh permissions are 600"
fi

# Cleanup
rm -rf "$TEST_DIR"
