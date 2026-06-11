#!/usr/bin/env bats
# Minimal coverage for configs/claude/scripts/browser_test.sh (specs/003 T035a:
# explicitly included rather than descoped). Covers subcommand routing, YAML
# validation, and the missing-browser-use skip path — no real browser runs.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/browser_test.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/browser_test.XXXXXX")
    mkdir -p "$SANDBOX/tests"
    cat > "$SANDBOX/tests/ok.yaml" <<'EOF'
task: "Open the homepage and confirm the title is visible"
max_steps: 5
judge_context:
  - "Title element is present"
EOF
    cat > "$SANDBOX/tests/bad.yaml" <<'EOF'
max_steps: 99
EOF
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "shows usage with no arguments" {
    run bash "$SCRIPT"
    assert_failure
    assert_output --partial "SUBCOMMANDS"
}

@test "unknown subcommand fails with usage" {
    run bash "$SCRIPT" bogus
    assert_failure
}

@test "validate accepts a well-formed YAML test file" {
    run bash "$SCRIPT" validate "$SANDBOX/tests/ok.yaml"
    assert_success
    assert_output --partial "VALID"
}

@test "validate rejects YAML missing task and with out-of-range max_steps" {
    run bash "$SCRIPT" validate "$SANDBOX/tests/bad.yaml"
    assert_failure
    assert_output --partial "INVALID"
}

@test "validate handles a path containing a single quote (FR-009)" {
    local qdir="$SANDBOX/it's here"
    mkdir -p "$qdir"
    cp "$SANDBOX/tests/ok.yaml" "$qdir/ok.yaml"
    run bash "$SCRIPT" validate "$qdir/ok.yaml"
    assert_success
    assert_output --partial "VALID"
}

@test "list shows test files in a directory of valid tests" {
    local vdir="$SANDBOX/valid-only"
    mkdir -p "$vdir"
    cp "$SANDBOX/tests/ok.yaml" "$vdir/ok.yaml"
    run bash "$SCRIPT" list "$vdir"
    assert_success
    assert_output --partial "ok.yaml"
}

@test "list aborts on first invalid file (current behavior under pipefail)" {
    # Pre-existing: the INVALID fallback pipeline (validate | head) fails under
    # set -o pipefail, so list exits non-zero on a dir with any invalid file.
    # Pinned as current behavior; flip if cmd_list is ever made fail-soft.
    run bash "$SCRIPT" list "$SANDBOX/tests"
    assert_failure
    assert_output --partial "INVALID"
}

@test "run exits 2 (skip) when browser-use is not installed" {
    # Hermetic PATH without browser-use; python3 import also absent.
    local mock_bin="$SANDBOX/bin"; mkdir -p "$mock_bin"
    for t in bash mkdir basename dirname cat grep sed date timeout; do
        p="$(command -v $t 2>/dev/null || true)"; [[ -n "$p" ]] && ln -s "$p" "$mock_bin/$t"
    done
    # Unquoted heredoc on purpose: $(command -v python3) resolves NOW, while
    # PATH is still full, embedding the real python3's absolute path — so the
    # exec passthrough works under the restricted PATH on any host.
    cat > "$mock_bin/python3" <<EOF
#!/usr/bin/env bash
if [[ "\$*" == *"import browser_use"* ]]; then exit 1; fi
exec "$(command -v python3)" "\$@"
EOF
    chmod +x "$mock_bin/python3"
    PATH="$mock_bin" run bash "$SCRIPT" run "$SANDBOX/tests/ok.yaml"
    [ "$status" -eq 2 ]
    assert_output --partial "not installed"
}
