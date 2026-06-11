#!/usr/bin/env bats
# Tests for configs/claude/scripts/label_sync.sh
# YAML parsing, dry-run output, platform detection, error handling

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../configs/claude/scripts/label_sync.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_DIR=$(mktemp -d "$BATS_TMPDIR/label_sync_test.XXXXXX")

    # Create a minimal labels.yml for testing
    mkdir -p "$TEST_DIR/config"
    cat > "$TEST_DIR/config/labels.yml" << 'EOF'
labels:
  - name: planned
    color: "1D76DB"
    description: "Implementation plan exists for this issue"
    platforms: [github, gitlab, linear]
  - name: done
    color: "0E8A16"
    description: "Implementation complete and validated"
    platforms: [github, gitlab, linear]

deprecated:
  - name: processed
    replacement: done
    reason: "Redundant with done"
EOF
}

teardown() {
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# --- Help and usage tests ---

@test "shows help with --help" {
    run bash "$SCRIPT_UNDER_TEST" --help
    assert_success
    assert_output --partial "Usage: label_sync.sh"
    assert_output --partial "--dry-run"
    assert_output --partial "--platform"
}

@test "fails on unknown option" {
    run bash "$SCRIPT_UNDER_TEST" --unknown-flag
    assert_failure
    assert_output --partial "Unknown option"
}

# --- Config file resolution tests ---

@test "fails when labels.yml not found" {
    run bash "$SCRIPT_UNDER_TEST" --config "/nonexistent/labels.yml"
    assert_failure
    assert_output --partial "Labels file not found"
}

@test "accepts explicit --config path" {
    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$TEST_DIR/config/labels.yml"
    assert_success
    assert_output --partial "Registry: $TEST_DIR/config/labels.yml"
}

@test "parses a labels.yml at a path containing a single quote (FR-009)" {
    # Path must be passed to Python as data (argv), never interpolated into
    # interpreter source — a quote in the path used to break/inject.
    local qdir="$TEST_DIR/it's here"
    mkdir -p "$qdir"
    cp "$TEST_DIR/config/labels.yml" "$qdir/labels.yml"

    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$qdir/labels.yml"
    assert_success
    assert_output --partial "Found 2 labels in registry"
}

# --- Dry-run tests ---

@test "dry-run lists all labels from registry" {
    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$TEST_DIR/config/labels.yml"
    assert_success
    assert_output --partial "Found 2 labels in registry"
    assert_output --partial "planned"
    assert_output --partial "done"
}

@test "dry-run shows would-create messages" {
    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$TEST_DIR/config/labels.yml"
    assert_success
    assert_output --partial "[dry-run]"
    assert_output --partial "Would create"
}

@test "dry-run reports zero created" {
    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$TEST_DIR/config/labels.yml"
    assert_success
    assert_output --partial "Created: 0"
}

# --- Validate-only tests ---

@test "validate mode shows would-create messages" {
    run bash "$SCRIPT_UNDER_TEST" --validate --config "$TEST_DIR/config/labels.yml"
    assert_success
    assert_output --partial "[dry-run]"
}

# --- Platform filter tests ---

@test "platform filter limits sync to specified platform" {
    run bash "$SCRIPT_UNDER_TEST" --dry-run --platform linear --config "$TEST_DIR/config/labels.yml"
    assert_success
    # Should only show linear messages, not git platform messages
    assert_output --partial "Linear"
}

# --- Invalid YAML tests ---

@test "fails on invalid YAML" {
    cat > "$TEST_DIR/config/bad.yml" << 'EOF'
labels:
  - name: planned
    color: "1D76DB
    description: unclosed quote
EOF
    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$TEST_DIR/config/bad.yml"
    assert_failure
}

# --- Empty labels file tests ---

@test "handles empty labels list" {
    cat > "$TEST_DIR/config/empty.yml" << 'EOF'
labels: []
EOF
    run bash "$SCRIPT_UNDER_TEST" --dry-run --config "$TEST_DIR/config/empty.yml"
    assert_success
    assert_output --partial "Found 0 labels"
}
