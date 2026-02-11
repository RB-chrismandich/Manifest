#!/usr/bin/env bats
# Tests for configs/claude/scripts/parallel_agent.sh
# Argument parsing, model selection, mode flags, exit codes

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../configs/claude/scripts/parallel_agent.sh"

setup() {
    # Create a temporary directory for each test
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/parallel_agent_test.XXXXXX")

    # Create mock bin directory for stub commands
    MOCK_BIN=$(mktemp -d "$BATS_TMPDIR/parallel_agent_mockbin.XXXXXX")
    export PATH="$MOCK_BIN:$PATH"

    # Isolate HOME so services.yml is not loaded from the real home
    MOCK_HOME=$(mktemp -d "$BATS_TMPDIR/parallel_agent_home.XXXXXX")
    export HOME="$MOCK_HOME"

    # Create a minimal state directory so the script can initialize
    export MANIFEST_STATE_ROOT="$TEST_DIR/manifest_state"
    export MANIFEST_TMP_DIR="$MANIFEST_STATE_ROOT/tmp"
    mkdir -p "$MANIFEST_STATE_ROOT" "$MANIFEST_TMP_DIR"

    # Stub agent CLIs to avoid real execution
    create_agent_stub "cursor"
    create_agent_stub "gemini"
    create_agent_stub "claude"
    create_agent_stub "codex"

    # Stub tput (used by monitor_agents)
    create_stub "tput"

    # Stub gtimeout / timeout
    create_stub "gtimeout"
}

teardown() {
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
    if [[ -n "$MOCK_BIN" && -d "$MOCK_BIN" ]]; then
        rm -rf "$MOCK_BIN"
    fi
    if [[ -n "$MOCK_HOME" && -d "$MOCK_HOME" ]]; then
        rm -rf "$MOCK_HOME"
    fi
}

# Helper: create a generic stub command
create_stub() {
    local cmd_name="$1"
    local exit_code="${2:-0}"
    cat > "$MOCK_BIN/$cmd_name" << STUB
#!/usr/bin/env bash
exit $exit_code
STUB
    chmod +x "$MOCK_BIN/$cmd_name"
}

# Helper: create an agent stub that writes dummy output
create_agent_stub() {
    local cmd_name="$1"
    cat > "$MOCK_BIN/$cmd_name" << STUB
#!/usr/bin/env bash
echo "Mock output from $cmd_name agent"
exit 0
STUB
    chmod +x "$MOCK_BIN/$cmd_name"
}

# --- Help / usage tests ---

@test "shows usage with --help flag" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "Parallel Agent Orchestration"
    assert_output --partial "Usage:"
}

@test "shows usage with -h flag" {
    run bash "$SCRIPT_UNDER_TEST" -h
    assert_success
    assert_output --partial "Parallel Agent Orchestration"
}

@test "help output lists --analyze option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--analyze"
}

@test "help output lists --review option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--review"
}

@test "help output lists --json option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--json"
}

@test "help output lists --timeout option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--timeout"
}

@test "help output lists --cursor-model option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--cursor-model"
}

@test "help output lists --claude-model option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--claude-model"
}

@test "help output lists --codex-model option" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "--codex-model"
}

# --- Missing arguments tests ---

@test "exits with code 1 when no prompt and no target given" {
    run bash "$SCRIPT_UNDER_TEST"
    assert_failure
    # Should show usage
    assert_output --partial "Usage:"
}

# --- Mode flag tests ---

@test "--review flag requires a file argument" {
    run bash "$SCRIPT_UNDER_TEST" --review
    assert_failure
    assert_output --partial "--review requires a file path"
}

@test "--review flag rejects option-like argument" {
    run bash "$SCRIPT_UNDER_TEST" --review --json
    assert_failure
    assert_output --partial "--review requires a file path"
}

@test "--analyze flag requires a file argument" {
    run bash "$SCRIPT_UNDER_TEST" --analyze
    assert_failure
    assert_output --partial "--analyze requires a file path"
}

@test "--analyze flag rejects option-like argument" {
    run bash "$SCRIPT_UNDER_TEST" --analyze --json
    assert_failure
    assert_output --partial "--analyze requires a file path"
}

@test "--improve flag requires a file argument" {
    run bash "$SCRIPT_UNDER_TEST" --improve
    assert_failure
    assert_output --partial "--improve requires a file path"
}

@test "--improve flag rejects option-like argument" {
    run bash "$SCRIPT_UNDER_TEST" --improve --json
    assert_failure
    assert_output --partial "--improve requires a file path"
}

# --- Agent selection flag tests ---

@test "--cursor-only disables other agents" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Cursor: enabled"
    refute_output --partial "Gemini: enabled"
    refute_output --partial "Claude: enabled"
    refute_output --partial "Codex: enabled"
}

@test "--gemini-only disables other agents" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --gemini-only --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Gemini: enabled"
    refute_output --partial "Cursor: enabled"
    refute_output --partial "Claude: enabled"
    refute_output --partial "Codex: enabled"
}

@test "--claude-only disables other agents" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --claude-only --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Claude: enabled"
    refute_output --partial "Cursor: enabled"
    refute_output --partial "Gemini: enabled"
    refute_output --partial "Codex: enabled"
}

@test "--codex-only disables other agents" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --codex-only --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Codex: enabled"
    refute_output --partial "Cursor: enabled"
    refute_output --partial "Gemini: enabled"
    refute_output --partial "Claude: enabled"
}

@test "--no-claude disables Claude agent" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --no-claude --review "$TEST_DIR/test_file.txt"
    refute_output --partial "Claude: enabled"
}

@test "--no-codex disables Codex agent" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --no-codex --review "$TEST_DIR/test_file.txt"
    refute_output --partial "Codex: enabled"
}

# --- Model selection tests ---

@test "--cursor-model requires a tier argument" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-model
    assert_failure
    assert_output --partial "--cursor-model requires a model tier"
}

@test "--cursor-model rejects option-like argument" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-model --json
    assert_failure
    assert_output --partial "--cursor-model requires a model tier"
}

@test "--claude-model requires a tier argument" {
    run bash "$SCRIPT_UNDER_TEST" --claude-model
    assert_failure
    assert_output --partial "--claude-model requires a model tier"
}

@test "--claude-model rejects option-like argument" {
    run bash "$SCRIPT_UNDER_TEST" --claude-model --json
    assert_failure
    assert_output --partial "--claude-model requires a model tier"
}

@test "--gemini-model requires a tier argument" {
    run bash "$SCRIPT_UNDER_TEST" --gemini-model
    assert_failure
    assert_output --partial "--gemini-model requires a model tier"
}

@test "--codex-model requires a tier argument" {
    run bash "$SCRIPT_UNDER_TEST" --codex-model
    assert_failure
    assert_output --partial "--codex-model requires a tier/model"
}

@test "--cursor-model mini sets model tier correctly" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --cursor-model mini --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Cursor: enabled (model: mini)"
}

@test "--cursor-model flash sets model tier correctly" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --cursor-model flash --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Cursor: enabled (model: flash)"
}

@test "--cursor-model advanced sets model tier correctly" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --cursor-model advanced --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Cursor: enabled (model: advanced)"
}

@test "--claude-model haiku sets model tier correctly" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --claude-only --claude-model haiku --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Claude: enabled (model: haiku)"
}

@test "--claude-model sonnet sets model tier correctly" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --claude-only --claude-model sonnet --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Claude: enabled (model: sonnet)"
}

@test "--claude-model opus sets model tier correctly" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --claude-only --claude-model opus --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Claude: enabled (model: opus)"
}

# --- Output format tests ---

@test "--json flag sets JSON output format" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --json --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Format: JSON"
}

@test "--full-output flag is acknowledged" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --full-output --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Full output: enabled"
}

@test "--validate flag is acknowledged" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --validate --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Validation: enabled"
}

# --- Timeout tests ---

@test "--timeout flag parses without error" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --timeout 300 --review "$TEST_DIR/test_file.txt"
    # Should not error on the timeout flag
    refute_output --partial "Unknown"
}

# --- Custom output directory tests ---

@test "--output flag sets custom output directory" {
    echo "test" > "$TEST_DIR/test_file.txt"
    local custom_dir="$TEST_DIR/custom_output"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --output "$custom_dir" --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Output: $custom_dir"
}

# --- No agents available test ---

@test "exits with code 2 when no agents are available" {
    echo "test" > "$TEST_DIR/test_file.txt"

    # Remove all agent stubs from PATH
    rm -f "$MOCK_BIN/cursor" "$MOCK_BIN/gemini" "$MOCK_BIN/claude" "$MOCK_BIN/codex"

    # Keep /usr/bin:/bin for system tools (bash, awk, etc.)
    run env PATH="$MOCK_BIN:/usr/bin:/bin" bash "$SCRIPT_UNDER_TEST" --review "$TEST_DIR/test_file.txt"
    assert_failure
    [[ "$status" -eq 2 ]]
    assert_output --partial "No agents available"
}

# --- File not found tests ---

@test "--review fails when target file does not exist" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-only --review "/nonexistent/file.py"
    assert_failure
    assert_output --partial "File not found"
}

@test "--analyze fails when target file does not exist" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-only --analyze "/nonexistent/file.py"
    assert_failure
    assert_output --partial "File not found"
}

@test "--improve fails when target file does not exist" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-only --improve "/nonexistent/file.yaml"
    assert_failure
    assert_output --partial "File not found"
}

# --- Prompt accumulation tests ---

@test "multiple positional arguments are joined into prompt" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-only "Hello" "world" "test"
    # The prompt is built from all positional args joined with spaces
    # This should not fail on argument parsing
    refute_output --partial "Unknown"
}

# --- Mode display tests ---

@test "review mode is displayed when --review is used" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --review "$TEST_DIR/test_file.txt"
    assert_output --partial "Mode: review"
}

@test "analyze mode is displayed when --analyze is used" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --analyze "$TEST_DIR/test_file.txt"
    assert_output --partial "Mode: analyze"
}

@test "prompt mode is the default" {
    run bash "$SCRIPT_UNDER_TEST" --cursor-only "Test question"
    assert_output --partial "Mode: prompt"
}

# --- State path display tests ---

@test "displays state path in output" {
    echo "test" > "$TEST_DIR/test_file.txt"

    run bash "$SCRIPT_UNDER_TEST" --cursor-only --review "$TEST_DIR/test_file.txt"
    assert_output --partial "State:"
}
