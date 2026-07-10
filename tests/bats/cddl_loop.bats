#!/usr/bin/env bats
# Tests for configs/claude/scripts/cddl_loop.py (feature 482, T024/T028/T031)
# CLI contract: --help, exit codes, pre-flight refusals, stubbed happy path,
# questions re-entry flow, superpowers discovery.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../configs/claude/scripts"
CDDL="$SCRIPTS_DIR/cddl_loop.py"

setup() {
    TEST_TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/cddl_test.XXXXXX")
    export HOME="$TEST_TMP/home"
    export MANIFEST_STATE_ROOT="$TEST_TMP/state"
    export TMPDIR="$TEST_TMP/tmp"
    mkdir -p "$HOME" "$TMPDIR"

    # Deploy the real role prompts into the fake home (runtime read location).
    mkdir -p "$HOME/.claude/prompts/cddl"
    cp "$SCRIPTS_DIR/../prompts/cddl/"*.md "$HOME/.claude/prompts/cddl/"

    # Stub `claude` on PATH: role-aware, phase-aware, deterministic.
    MOCK_BIN="$TEST_TMP/bin"
    mkdir -p "$MOCK_BIN"
    cat > "$MOCK_BIN/claude" << 'STUB'
#!/usr/bin/env bash
prompt=$(cat)
role="qa_critic"
[[ "$prompt" == *'"arch_critic"'* ]] && role="arch_critic"
if [[ "$prompt" == *"phase 1: clarification gate"* ]]; then
    if [[ -n "${CDDL_STUB_QUESTIONS:-}" && "$prompt" != *"Operator clarification answers"* ]]; then
        printf '```cddl-verdict\n{"role": "%s", "decision": "questions", "findings": [{"title": "limit", "detail": "what is the max size?"}]}\n```\n' "$role"
    else
        printf '```cddl-verdict\n{"role": "%s", "decision": "complete", "findings": []}\n```\n' "$role"
    fi
elif [[ "$prompt" == *"produce the candidate"* ]]; then
    printf 'Adding the greeting.\n```cddl-file greet.txt\nhello from cddl\n```\n'
else
    printf '```cddl-verdict\n{"role": "%s", "decision": "approve", "findings": []}\n```\n' "$role"
fi
STUB
    chmod +x "$MOCK_BIN/claude"
    export PATH="$MOCK_BIN:$PATH"

    # Fixture target repo: speckit layout, clean tree, feature branch.
    TEST_REPO="$TEST_TMP/repo"
    mkdir -p "$TEST_REPO/specs/001-fixture"
    git init -q -b main "$TEST_REPO"
    git -C "$TEST_REPO" config user.email cddl@test
    git -C "$TEST_REPO" config user.name cddl-test
    printf '# Spec\nGreet the user.\n' > "$TEST_REPO/specs/001-fixture/spec.md"
    printf '# Plan\nOne file.\n' > "$TEST_REPO/specs/001-fixture/plan.md"
    git -C "$TEST_REPO" add -A
    git -C "$TEST_REPO" commit -qm init
    git -C "$TEST_REPO" checkout -qb 482-fixture
}

teardown() {
    [[ -n "$TEST_TMP" && -d "$TEST_TMP" ]] && rm -rf "$TEST_TMP"
}

# --- help + usage contract (FR-016) ---

@test "cddl_loop --help exits 0 within 15 lines" {
    run python3 "$CDDL" --help
    assert_success
    assert_output --partial "Usage: cddl_loop.py"
    [ "$(echo "$output" | wc -l)" -le 15 ]
}

@test "cddl_loop with no args is a usage error (exit 2)" {
    run python3 "$CDDL"
    [ "$status" -eq 2 ]
}

@test "cddl_loop unknown subcommand is a usage error (exit 2)" {
    run python3 "$CDDL" frobnicate
    [ "$status" -eq 2 ]
}

# --- pre-flight refusals (exit 6, FR-011/FR-012/FR-013, T024) ---

@test "start on default branch refused with exit 6" {
    git -C "$TEST_REPO" checkout -q main
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 6 ]
    assert_output --partial "default branch"
}

@test "start on dirty tree refused with exit 6" {
    echo dirt > "$TEST_REPO/uncommitted.txt"
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 6 ]
    assert_output --partial "dirty"
}

@test "start with invalid role file refused with exit 6 naming the file" {
    printf -- '---\nname: wrong-stem\ndescription: x\nmodel: sonnet\n---\nbody\n' \
        > "$HOME/.claude/prompts/cddl/qa-critic.md"
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 6 ]
    assert_output --partial "qa-critic.md"
}

@test "start on unresolvable target refused, names both layouts" {
    mkdir -p "$TEST_REPO/not-a-feature"
    run python3 "$CDDL" start "$TEST_REPO/not-a-feature"
    [ "$status" -eq 6 ]
    assert_output --partial "speckit"
    assert_output --partial "superpowers"
}

@test "start without usable backend refused with exit 6 (FR-012)" {
    export CDDL_CLI="definitely-not-a-real-cli-xyz"
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 6 ]
    assert_output --partial "no usable backend"
}

@test "held lock refused with exit 6" {
    slug=$(python3 -c "import sys; sys.path.insert(0, '$SCRIPTS_DIR'); from cddl.persistence import repo_slug; print(repo_slug('$TEST_REPO'))")
    mkdir -p "$MANIFEST_STATE_ROOT/cddl/locks"
    printf '{"pid": 1, "run": "other-run"}' > "$MANIFEST_STATE_ROOT/cddl/locks/$slug.lock"
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 6 ]
    assert_output --partial "active"
    assert_output --partial "other-run"   # contract: message names the owning run
}

@test "start with logged-out backend refused with exit 6 (FR-012 auth probe)" {
    cat > "$MOCK_BIN/claude" << 'STUB'
#!/usr/bin/env bash
if [ "$1" = "auth" ]; then printf '{"loggedIn": false}\n'; exit 1; fi
cat > /dev/null; echo "should never be invoked"
STUB
    chmod +x "$MOCK_BIN/claude"
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 6 ]
    assert_output --partial "not logged in"
}

# --- stubbed happy path (US1 independent test) ---

@test "happy path: exit 0, file staged, report exists, no commit" {
    head_before=$(git -C "$TEST_REPO" rev-parse HEAD)
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    assert_success
    run git -C "$TEST_REPO" diff --cached --name-only
    assert_output --partial "greet.txt"
    [ "$(git -C "$TEST_REPO" rev-parse HEAD)" = "$head_before" ]
    report=$(find "$MANIFEST_STATE_ROOT/cddl/runs" -name report.md | head -1)
    [ -n "$report" ]
    grep -q "success" "$report"
}

# --- questions re-entry flow (US2, T028) ---

@test "questions flow: exit 3, questions.md, answer re-entry completes" {
    export CDDL_STUB_QUESTIONS=1
    run python3 "$CDDL" start "$TEST_REPO/specs/001-fixture"
    [ "$status" -eq 3 ]
    questions=$(find "$MANIFEST_STATE_ROOT/cddl/runs" -name questions.md | head -1)
    [ -n "$questions" ]
    grep -q "max size" "$questions"

    run_id=$(basename "$(dirname "$questions")")
    printf 'The max size is 10MB.\n' > "$TEST_TMP/answers.md"
    cd "$TEST_REPO"
    run python3 "$CDDL" answer --run "$run_id" --answers-file "$TEST_TMP/answers.md"
    assert_success
    run git -C "$TEST_REPO" diff --cached --name-only
    assert_output --partial "greet.txt"
}

# --- superpowers layout + status (US3, T031) ---

@test "superpowers layout runs identically" {
    SP_REPO="$TEST_TMP/sp-repo"
    mkdir -p "$SP_REPO/docs/superpowers/specs" "$SP_REPO/docs/superpowers/plans"
    git init -q -b main "$SP_REPO"
    git -C "$SP_REPO" config user.email cddl@test
    git -C "$SP_REPO" config user.name cddl-test
    printf '# Design\nGreet the user.\n' > "$SP_REPO/docs/superpowers/specs/2026-fixture-design.md"
    printf '# Plan\nTasks embedded.\n' > "$SP_REPO/docs/superpowers/plans/2026-fixture-plan.md"
    git -C "$SP_REPO" add -A && git -C "$SP_REPO" commit -qm init
    git -C "$SP_REPO" checkout -qb 482-sp
    run python3 "$CDDL" start "$SP_REPO"
    assert_success
    run git -C "$SP_REPO" diff --cached --name-only
    assert_output --partial "greet.txt"
    state=$(find "$MANIFEST_STATE_ROOT/cddl/runs" -name state.json | head -1)
    grep -q '"layout_type": "superpowers"' "$state"
}

@test "status summarizes the latest run" {
    python3 "$CDDL" start "$TEST_REPO/specs/001-fixture" > /dev/null
    cd "$TEST_REPO"
    run python3 "$CDDL" status
    assert_success
    assert_output --partial "status:   success"
    run python3 "$CDDL" status --run does-not-exist
    [ "$status" -eq 6 ]
}
