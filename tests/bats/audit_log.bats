#!/usr/bin/env bats
# Tests for configs/claude/scripts/audit_log.sh

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/audit_log.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/audit_log.XXXXXX")
    export AUTO_ISSUE_DEV_AUDIT_FILE="$TMP/audit.jsonl"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# --- CLI surface ---

@test "--help exits 0 and prints usage" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"append"* ]]
    [[ "$output" == *"redact"* ]]
}

@test "unknown subcommand exits non-zero" {
    run "$SCRIPT" bogus
    [ "$status" -ne 0 ]
    [[ "$output" == *"audit-log:"* ]]
}

# --- redact subcommand ---

@test "redact: masks GitHub PAT (ghp_...)" {
    run "$SCRIPT" redact '{"token":"ghp_abcdefghijklmnopqrstuvwxyz123456"}'
    [ "$status" -eq 0 ]
    [[ "$output" != *"ghp_"* ]]
    [[ "$output" == *"REDACTED"* ]]
}

@test "redact: masks GitHub OAuth token (gho_...)" {
    run "$SCRIPT" redact '{"auth":"gho_abcdefghijklmnopqrstuvwxyz123456"}'
    [ "$status" -eq 0 ]
    [[ "$output" != *"gho_"* ]]
    [[ "$output" == *"REDACTED"* ]]
}

@test "redact: masks Anthropic API key (sk-ant-...)" {
    run "$SCRIPT" redact 'key=sk-ant-api03-aaaabbbbccccddddeeeeffffgggghhhh'
    [ "$status" -eq 0 ]
    [[ "$output" != *"sk-ant-"* ]]
    [[ "$output" == *"REDACTED"* ]]
}

@test "redact: masks OpenAI-style API key (sk-...)" {
    run "$SCRIPT" redact 'key=sk-aaaaaabbbbbbccccccddddddeeeeeeffffffffgggggghh'
    [ "$status" -eq 0 ]
    [[ "$output" != *"sk-aaaaa"* ]]
    [[ "$output" == *"REDACTED"* ]]
}

@test "redact: masks generic token=value pattern" {
    run "$SCRIPT" redact 'token=supersecret123'
    [ "$status" -eq 0 ]
    [[ "$output" != *"supersecret123"* ]]
    [[ "$output" == *"REDACTED"* ]]
}

@test "redact: masks Bearer authorization header" {
    run "$SCRIPT" redact 'Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig'
    [ "$status" -eq 0 ]
    [[ "$output" != *"eyJhbGci"* ]]
    [[ "$output" == *"REDACTED"* ]]
}

@test "redact: passes clean text unchanged" {
    run "$SCRIPT" redact '{"issue":42,"action":"pr-opened","outcome":"PR #99"}'
    [ "$status" -eq 0 ]
    [[ "$output" == *'"issue":42'* ]]
    [[ "$output" == *'"action":"pr-opened"'* ]]
    [[ "$output" != *"REDACTED"* ]]
}

# --- append subcommand ---

@test "append: creates audit file and writes one JSON line" {
    run "$SCRIPT" append '{"issue":1,"action":"pr-opened"}'
    [ "$status" -eq 0 ]
    [ -f "$AUTO_ISSUE_DEV_AUDIT_FILE" ]
    [ "$(wc -l < "$AUTO_ISSUE_DEV_AUDIT_FILE")" -eq 1 ]
    python3 -c "import json; json.loads(open('$AUTO_ISSUE_DEV_AUDIT_FILE').read())"
}

@test "append: second call appends without mutating first line" {
    "$SCRIPT" append '{"issue":1,"action":"pr-opened"}'
    first="$(head -1 "$AUTO_ISSUE_DEV_AUDIT_FILE")"
    run "$SCRIPT" append '{"issue":2,"action":"draft-pr"}'
    [ "$status" -eq 0 ]
    [ "$(wc -l < "$AUTO_ISSUE_DEV_AUDIT_FILE")" -eq 2 ]
    [ "$(head -1 "$AUTO_ISSUE_DEV_AUDIT_FILE")" = "$first" ]
}

@test "append: redacts secrets present in the record before writing" {
    run "$SCRIPT" append '{"issue":3,"token":"ghp_abcdefghijklmnopqrstuvwxyz123456"}'
    [ "$status" -eq 0 ]
    [ -f "$AUTO_ISSUE_DEV_AUDIT_FILE" ]
    ! grep -q "ghp_" "$AUTO_ISSUE_DEV_AUDIT_FILE"
    grep -q "REDACTED" "$AUTO_ISSUE_DEV_AUDIT_FILE"
}

@test "append: fails open when file path is not writable (exit 0, no crash)" {
    export AUTO_ISSUE_DEV_AUDIT_FILE="/dev/full"
    run "$SCRIPT" append '{"issue":4,"action":"pr-opened"}'
    [ "$status" -eq 0 ]
}

@test "append: fails open when parent directory cannot be created (exit 0)" {
    export AUTO_ISSUE_DEV_AUDIT_FILE="/nonexistent-root/deeply/nested/audit.jsonl"
    run "$SCRIPT" append '{"issue":5,"action":"pr-opened"}'
    [ "$status" -eq 0 ]
}
