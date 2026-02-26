#!/bin/bash

# Test script for write_file_securely

# Source the common library
source bootstrap/lib/common.sh

TEST_DIR="tests/secure_write_test"
mkdir -p "$TEST_DIR"
trap 'rm -rf "$TEST_DIR"' EXIT

echo "Testing write_file_securely..."

# Test 1: Write with content argument
FILE1="$TEST_DIR/file1"
CONTENT1="Secret content 1"

if write_file_securely "$FILE1" "$CONTENT1"; then
    echo "PASS: write_file_securely (arg) succeeded"
else
    echo "FAIL: write_file_securely (arg) failed"
    exit 1
fi

if [[ "$(cat "$FILE1")" == "$CONTENT1" ]]; then
    echo "PASS: Content matches"
else
    echo "FAIL: Content mismatch. Expected '$CONTENT1', got '$(cat "$FILE1")'"
    exit 1
fi

# Check permissions (Linux/macOS compatible check)
if [[ "$OSTYPE" == "darwin"* ]]; then
    PERMS=$(stat -f "%Lp" "$FILE1")
else
    PERMS=$(stat -c "%a" "$FILE1")
fi

if [[ "$PERMS" == "600" ]]; then
    echo "PASS: Permissions are 600"
else
    echo "FAIL: Permissions are $PERMS, expected 600"
    exit 1
fi

# Test 2: Write with stdin
FILE2="$TEST_DIR/file2"
CONTENT2="Secret content 2"

echo "$CONTENT2" | write_file_securely "$FILE2"

if [[ -f "$FILE2" ]]; then
    echo "PASS: write_file_securely (stdin) succeeded"
else
    echo "FAIL: write_file_securely (stdin) failed"
    exit 1
fi

if [[ "$(cat "$FILE2")" == "$CONTENT2" ]]; then
    echo "PASS: Content matches"
else
    echo "FAIL: Content mismatch. Expected '$CONTENT2', got '$(cat "$FILE2")'"
    exit 1
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    PERMS=$(stat -f "%Lp" "$FILE2")
else
    PERMS=$(stat -c "%a" "$FILE2")
fi

if [[ "$PERMS" == "600" ]]; then
    echo "PASS: Permissions are 600"
else
    echo "FAIL: Permissions are $PERMS, expected 600"
    exit 1
fi

# Test 3: Overwrite existing file
echo "Old content" > "$FILE1"
chmod 777 "$FILE1"

write_file_securely "$FILE1" "$CONTENT1"

if [[ "$(cat "$FILE1")" == "$CONTENT1" ]]; then
    echo "PASS: Overwrite content matches"
else
    echo "FAIL: Overwrite content mismatch"
    exit 1
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    PERMS=$(stat -f "%Lp" "$FILE1")
else
    PERMS=$(stat -c "%a" "$FILE1")
fi

if [[ "$PERMS" == "600" ]]; then
    echo "PASS: Overwrite permissions are 600"
else
    echo "FAIL: Overwrite permissions are $PERMS, expected 600"
    exit 1
fi

echo "All tests passed!"
