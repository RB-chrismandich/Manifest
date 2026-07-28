#!/usr/bin/env bats
# #547/#552 regression guard: the token-benchmark SKILL.md Execution block must
# not wrap --cli-only or --report-only invocations in `uv run --group benchmark`.
# Doing so forces uv dependency resolution/installation before harness.py's own
# argument parsing/guard logic even runs, contradicting the documented and
# tested guarantee that --cli-only needs no SDK (and no uv at all).
#
# This test extracts the actual bash block from SKILL.md's "## Execution"
# section and executes it (unlike TestMainSdkGuard.test_cli_only_runs_without_sdks
# in tests/python/token_benchmark/test_harness.py, which calls harness.main()
# directly in-process and never goes through this wrapper), with `uv` stubbed
# to fail loudly — simulating an empty cache / no network — so any invocation
# of `uv` is both visible in the call log and fatal to the run.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SKILL_MD="$REPO_ROOT/.apm/skills/token-benchmark/SKILL.md"

# Pulls out the fenced ```bash block that immediately follows "## Execution".
extract_execution_block() {
    awk '
        /^## Execution/ { found=1 }
        found && /^```bash/ { incode=1; next }
        incode && /^```/ { exit }
        incode { print }
    ' "$SKILL_MD"
}

setup() {
    SANDBOX="$(mktemp -d)"
    extract_execution_block > "$SANDBOX/execution.sh"

    MOCK_BIN="$SANDBOX/bin"
    mkdir -p "$MOCK_BIN"
    CALL_LOG="$SANDBOX/calls.log"
    export CALL_LOG

    # uv "fails" the way it did in the reported repro: empty cache, no network,
    # dependency resolution can't complete. Any call must be visible AND fatal.
    cat > "$MOCK_BIN/uv" << 'EOF'
#!/usr/bin/env bash
echo "uv $*" >> "$CALL_LOG"
exit 1
EOF
    # python3 just records how it was invoked; harness.py doesn't need to
    # actually run for this test — we only care which interpreter was chosen.
    cat > "$MOCK_BIN/python3" << 'EOF'
#!/usr/bin/env bash
echo "python3 $*" >> "$CALL_LOG"
exit 0
EOF
    chmod +x "$MOCK_BIN/uv" "$MOCK_BIN/python3"

    export SANDBOX MOCK_BIN
}

teardown() {
    rm -rf "$SANDBOX"
}

@test "SKILL.md Execution block exists and is non-empty" {
    [ -s "$SANDBOX/execution.sh" ]
}

@test "--cli-only --report-only never invokes uv, exits 0" {
    ARGUMENTS="--cli-only --providers antigravity --report-only"
    run env PATH="$MOCK_BIN:$PATH" ARGUMENTS="$ARGUMENTS" bash "$SANDBOX/execution.sh"
    assert_success
    run grep -c '^uv ' "$CALL_LOG"
    assert_output "0"
    run grep -c '^python3 ' "$CALL_LOG"
    assert_output "1"
}

@test "--cli-only (no report-only) never invokes uv, exits 0" {
    ARGUMENTS="--cli-only --providers antigravity"
    run env PATH="$MOCK_BIN:$PATH" ARGUMENTS="$ARGUMENTS" bash "$SANDBOX/execution.sh"
    assert_success
    run grep -c '^uv ' "$CALL_LOG"
    assert_output "0"
    run grep -c '^python3 ' "$CALL_LOG"
    assert_output "1"
    run grep '^python3 ' "$CALL_LOG"
    assert_output --partial -- "--cli-only"
}

@test "--report-only alone never invokes uv, exits 0" {
    ARGUMENTS="--report-only"
    run env PATH="$MOCK_BIN:$PATH" ARGUMENTS="$ARGUMENTS" bash "$SANDBOX/execution.sh"
    assert_success
    run grep -c '^uv ' "$CALL_LOG"
    assert_output "0"
}

@test "default mode (API path in play) does invoke uv run --group benchmark" {
    ARGUMENTS="--providers claude"
    run env PATH="$MOCK_BIN:$PATH" ARGUMENTS="$ARGUMENTS" bash "$SANDBOX/execution.sh"
    # uv is stubbed to fail (exit 1): a run that legitimately needs the API
    # path must reach uv and fail there, proving uv IS exercised for this mode.
    assert_failure
    run grep -c '^uv .*--group benchmark' "$CALL_LOG"
    assert_output "1"
    run grep -c '^python3 ' "$CALL_LOG"
    assert_output "0"
}

@test "--api-only (API path in play) does invoke uv run --group benchmark" {
    ARGUMENTS="--api-only --providers claude,gemini"
    run env PATH="$MOCK_BIN:$PATH" ARGUMENTS="$ARGUMENTS" bash "$SANDBOX/execution.sh"
    assert_failure
    run grep -c '^uv .*--group benchmark' "$CALL_LOG"
    assert_output "1"
}
