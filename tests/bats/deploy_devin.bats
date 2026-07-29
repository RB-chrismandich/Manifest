#!/usr/bin/env bats
# Tests for Devin CLI config wiring (deploy_devin_config).
#
# Devin is deliberately NOT a mirrored config tree like Cursor/Gemini/Codex/
# Antigravity. Measured against devin 3000.2.17 (2026-07-29):
#   - the CLI discovers ~/.claude/skills and ~/.claude/CLAUDE.md on its own,
#     gated by config.json's `read_config_from.claude`;
#   - a second copy of the skills under its own home does not add a skill, it
#     registers every skill twice (/devin:<name> beside /claude:<name>).
# So deploy ships exactly one thing: the inheritance pin. These tests hold that
# line — no skills dir, no clobbered user config, no silent override.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/deploy_devin.XXXXXX")
    export TARGET_DIR="$SANDBOX/dotclaude"
    export DEVIN_TARGET_DIR="$SANDBOX/config/devin"
    export ENABLE_DEVIN=true
    mkdir -p "$TARGET_DIR/skills"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

read_claude_flag() {
    python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['read_config_from']['claude'])" "$1"
}

@test "disabled devin deploys nothing at all" {
    export ENABLE_DEVIN=false
    run deploy_devin_config
    assert_success
    [ ! -e "$DEVIN_TARGET_DIR/config.json" ]
    [ ! -d "$DEVIN_TARGET_DIR" ]
}

@test "fresh install writes a config.json pinning claude inheritance" {
    run deploy_devin_config
    assert_success
    [ -f "$DEVIN_TARGET_DIR/config.json" ]
    assert_equal "$(read_claude_flag "$DEVIN_TARGET_DIR/config.json")" "True"
}

@test "never creates a skills directory under the devin home (no double-registration)" {
    run deploy_devin_config
    assert_success
    [ ! -e "$DEVIN_TARGET_DIR/skills" ]
}

@test "existing user config keys survive the merge" {
    mkdir -p "$DEVIN_TARGET_DIR"
    cat > "$DEVIN_TARGET_DIR/config.json" << 'EOF'
{
  "model": "swe-1-6-fast",
  "permissions": { "deny": ["Exec(sudo)"] },
  "mcpServers": { "sentry": { "transport": "http" } }
}
EOF
    run deploy_devin_config
    assert_success
    assert_equal "$(read_claude_flag "$DEVIN_TARGET_DIR/config.json")" "True"
    run python3 -c "import json;d=json.load(open('$DEVIN_TARGET_DIR/config.json'));print(d['model'],list(d['permissions']),list(d['mcpServers']))"
    assert_output --partial "swe-1-6-fast"
    assert_output --partial "deny"
    assert_output --partial "sentry"
}

@test "an explicit read_config_from.claude=false is reported, not overridden" {
    mkdir -p "$DEVIN_TARGET_DIR"
    printf '{ "read_config_from": { "claude": false } }\n' > "$DEVIN_TARGET_DIR/config.json"
    run deploy_devin_config
    assert_success
    assert_output --partial "will NOT load"
    assert_equal "$(read_claude_flag "$DEVIN_TARGET_DIR/config.json")" "False"
}

@test "re-running is idempotent and reports the pin as already present" {
    run deploy_devin_config
    assert_success
    local first
    first="$(cat "$DEVIN_TARGET_DIR/config.json")"
    run deploy_devin_config
    assert_success
    assert_output --partial "already reads"
    assert_equal "$(cat "$DEVIN_TARGET_DIR/config.json")" "$first"
}

@test "an unreadable/invalid config.json is never clobbered" {
    mkdir -p "$DEVIN_TARGET_DIR"
    printf 'this is not json' > "$DEVIN_TARGET_DIR/config.json"
    run deploy_devin_config
    assert_success
    assert_output --partial "Could not update"
    assert_equal "$(cat "$DEVIN_TARGET_DIR/config.json")" "this is not json"
}
