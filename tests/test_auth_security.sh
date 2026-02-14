#!/bin/bash
set -e

# Mock UI functions
print_step() { echo "[STEP] $1"; }
print_success() { echo "[SUCCESS] $1"; }
print_warning() { echo "[WARNING] $1"; }
print_error() { echo "[ERROR] $1"; }
command_exists() { return 1; } # Mock command check

# Colors
BOLD=""
NC=""
CYAN=""
RED=""
GREEN=""
BLUE=""
YELLOW=""

# Test Directory
TEST_DIR=$(mktemp -d)
TARGET_DIR="$TEST_DIR/.claude"
mkdir -p "$TARGET_DIR"

# Source the function
source "bootstrap/lib/auth.sh"

# Run the test
# We simulate user input:
# 1. Option "2" (API Key)
# 2. The API Key "test-api-key-123"

echo "Running setup_gemini_auth test..."

# Use subshell to feed input
(echo "2"; echo "test-api-key-123") | setup_gemini_auth

ENV_FILE="$TARGET_DIR/gemini_env.sh"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "FAILED: $ENV_FILE does not exist"
    exit 1
fi

# Check content
if grep -q "export GEMINI_API_KEY='test-api-key-123'" "$ENV_FILE"; then
    echo "Content verification: PASSED"
else
    echo "Content verification: FAILED"
    cat "$ENV_FILE"
    exit 1
fi

# Check permissions
if [[ "$OSTYPE" == "darwin"* ]]; then
    PERMS=$(stat -f "%Lp" "$ENV_FILE")
else
    PERMS=$(stat -c "%a" "$ENV_FILE")
fi

if [[ "$PERMS" == "600" ]]; then
    echo "Permission verification: PASSED (600)"
else
    echo "Permission verification: FAILED (Expected 600, got $PERMS)"
    ls -l "$ENV_FILE"
    exit 1
fi

# Cleanup
rm -rf "$TEST_DIR"
echo "ALL TESTS PASSED"
