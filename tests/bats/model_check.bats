#!/usr/bin/env bats
# Tests for configs/claude/scripts/model_check.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/model_check.sh"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/model_check.XXXXXX")
    cat > "$SANDBOX/pa.yml" <<'EOF'
model_tiers:
  antigravity:
    flash: "Gemini 3.5 Flash (High)"
    advanced: "Claude Opus 4.6 (Thinking)"
  codex:
    mini: "gpt-5.4-mini"
EOF
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "model_check.sh exits 0 even with no providers available" {
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml" PATH="/usr/bin:/bin" run bash "$SCRIPT"
    assert_success
}

@test "list_tiers emits tier/model pairs from config" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run list_tiers antigravity
    assert_success
    assert_output --partial "flash	Gemini 3.5 Flash (High)"
    assert_output --partial "advanced	Claude Opus 4.6 (Thinking)"
}

@test "check_cli_provider reports OK for models present in listing" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<'EOF'
#!/usr/bin/env bash
printf 'Gemini 3.5 Flash (High)\nClaude Opus 4.6 (Thinking)\n'
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy"
    assert_success
    assert_output --partial "OK: model_tiers.antigravity.flash"
    assert_output --partial "OK: model_tiers.antigravity.advanced"
}

@test "check_cli_provider reports STALE for models missing from listing" {
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/fakeagy" <<'EOF'
#!/usr/bin/env bash
printf 'Gemini 9 Ultra\n'
EOF
    chmod +x "$SANDBOX/bin/fakeagy"
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/fakeagy" "$SANDBOX/bin/fakeagy"
    assert_success
    assert_output --partial "STALE: model_tiers.antigravity.flash = Gemini 3.5 Flash (High) not in provider listing"
}

@test "check_cli_provider skips when binary is missing" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    run check_cli_provider antigravity "$SANDBOX/bin/nope" "$SANDBOX/bin/nope"
    assert_success
    assert_output --partial "SKIPPED: antigravity"
}

@test "check_api_provider skips without credentials" {
    source "$SCRIPT"
    MODEL_CHECK_CONFIG="$SANDBOX/pa.yml"
    ANTHROPIC_API_KEY="" run check_api_provider claude
    assert_success
    assert_output --partial "SKIPPED: claude (no credentials)"
}
