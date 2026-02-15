#!/bin/bash
set -e

# Setup mock environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SCRIPT_DIR
export TARGET_DIR=$(mktemp -d)
export ENABLE_GEMINI=true

# Mock colors for sourced scripts
export RED=""
export GREEN=""
export BLUE=""
export YELLOW=""
export CYAN=""
export BOLD=""
export NC=""

# Source required libraries
source "$SCRIPT_DIR/bootstrap/lib/common.sh"
source "$SCRIPT_DIR/bootstrap/lib/auth.sh"

echo "Testing setup_gemini_auth in $TARGET_DIR"

# Simulate user input:
# 2 (Select API Key option)
# my-secret-api-key (The key)
printf "2\nmy-secret-api-key\n" | setup_gemini_auth > /dev/null

OUTPUT_FILE="$TARGET_DIR/gemini_env.sh"

# Check if file exists
if [[ ! -f "$OUTPUT_FILE" ]]; then
    echo "Error: File $OUTPUT_FILE not created"
    rm -rf "$TARGET_DIR"
    exit 1
fi

# Check permissions
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS stat
    PERMS=$(stat -f %Lp "$OUTPUT_FILE")
else
    # Linux stat
    PERMS=$(stat -c %a "$OUTPUT_FILE")
fi

echo "File permissions: $PERMS"

if [[ "$PERMS" != "600" ]]; then
    echo "Error: File permissions are $PERMS, expected 600"
    rm -rf "$TARGET_DIR"
    exit 1
fi

# Check content
CONTENT=$(cat "$OUTPUT_FILE")
EXPECTED="export GEMINI_API_KEY='my-secret-api-key'"

if [[ "$CONTENT" != *"$EXPECTED"* ]]; then
    echo "Error: File content does not match expected."
    echo "Expected: $EXPECTED"
    echo "Actual: $CONTENT"
    rm -rf "$TARGET_DIR"
    exit 1
fi

echo "Success: File created with correct permissions and content."
rm -rf "$TARGET_DIR"
exit 0
