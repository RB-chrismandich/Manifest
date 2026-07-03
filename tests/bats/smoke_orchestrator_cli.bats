#!/usr/bin/env bats
# CLI entry-point + skill-wrapper tests for the smoke-test orchestrator (T033).
# --help must succeed before any runtime dependency (PyYAML/Playwright) is touched;
# the gate's exit codes (0/1/2) are verified through the real shim binary.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
SHIM="$REPO_ROOT/configs/claude/scripts/smoke_test.py"
CLI_TOOL="$REPO_ROOT/tests/python/smoke_orchestrator/fixtures/cli_tool.py"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/smoke_cli.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

needs_pyyaml() {
    python3 -c "import yaml" 2>/dev/null || skip "PyYAML not installed (opt-in smoke dep)"
}

write_catalog() {  # $1 tier  $2 cli_tool subcommand
    mkdir -p "$SANDBOX/cat"
    cat > "$SANDBOX/cat/demo.yaml" <<YAML
version: 1
app: demo
tests:
  - id: t1
    tier: $1
    steps:
      - {name: s, type: cli, command: ["$(command -v python3)", "$CLI_TOOL", "$2"]}
YAML
}

# --- --help precedes any dependency lookup (cli-audit-help) ---
@test "smoke_test.py --help exits 0 with usage (clean HOME, no catalog)" {
    run env HOME="$SANDBOX" "$SHIM" --help
    assert_success
    assert_output --partial "usage:"
    assert_output --partial "append"
    assert_output --partial "run"
}

@test "every subcommand --help exits 0 with usage" {
    for sub in append run list prune; do
        run "$SHIM" "$sub" --help
        assert_success
        assert_output --partial "usage:"
    done
}

# --- gate exit codes 0 / 1 / 2 ---
@test "run exits 0 when the selected test passes (and writes JUnit)" {
    needs_pyyaml
    write_catalog Lite ok
    run "$SHIM" run --app demo --tier Lite --catalog-dir "$SANDBOX/cat" --junit "$SANDBOX/r.xml"
    assert_success
    [ -f "$SANDBOX/r.xml" ]
}

@test "run exits 1 when a selected test fails" {
    needs_pyyaml
    write_catalog Lite fail
    run "$SHIM" run --app demo --tier Lite --catalog-dir "$SANDBOX/cat" --junit ""
    [ "$status" -eq 1 ]
}

@test "run exits 2 on empty selection (Lite over a Full-only catalog)" {
    needs_pyyaml
    write_catalog Full ok
    run "$SHIM" run --app demo --tier Lite --catalog-dir "$SANDBOX/cat" --junit ""
    [ "$status" -eq 2 ]
}

@test "run exits 2 on an unknown tier (usage error)" {
    needs_pyyaml
    write_catalog Lite ok
    run "$SHIM" run --app demo --tier Mega --catalog-dir "$SANDBOX/cat" --junit ""
    [ "$status" -eq 2 ]
}

# --- append: idempotent + validation rejection ---
@test "append is idempotent by id and rejects invalid input (exit 2)" {
    needs_pyyaml
    printf '%s' '{"app":"demo","id":"a","tier":"Lite","steps":[{"name":"s","type":"api","method":"GET","path":"/health"}]}' \
        > "$SANDBOX/wf.json"
    run "$SHIM" append --from "$SANDBOX/wf.json" --catalog-dir "$SANDBOX/cat"
    assert_success
    run "$SHIM" append --from "$SANDBOX/wf.json" --catalog-dir "$SANDBOX/cat"
    assert_success
    run "$SHIM" list --app demo --json --catalog-dir "$SANDBOX/cat"
    assert_success
    assert_output --partial '"a"'

    printf '%s' '{"app":"demo","id":"b"}' > "$SANDBOX/bad.json"  # missing tier/steps
    run "$SHIM" append --from "$SANDBOX/bad.json" --catalog-dir "$SANDBOX/cat"
    [ "$status" -eq 2 ]
}

# --- skill wrapper present ---
@test "skill wrapper SKILL.md is present with name + description" {
    run cat "$REPO_ROOT/.skillshare/skills/smoke-manage/SKILL.md"
    assert_success
    assert_output --partial "name: smoke-manage"
    assert_output --partial "description:"
}
