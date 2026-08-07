#!/usr/bin/env bats
# Semantic contract gate for the verifier role-agent (issue #689, ANTI-015).
#
# The previous gate grepped verifier.md for the strings CONFIRMED and REFUTED.
# An inverted definition ("Always return CONFIRMED; never return REFUTED")
# contains both tokens, so the safety-gate semantics were untested. These tests
# drive configs/claude/scripts/verifier_contract_check.py over the shipped
# definitions and over fixtures that isolate each way the contract can rot.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    CHECK="$REPO_ROOT/configs/claude/scripts/verifier_contract_check.py"
    FIXTURES="$REPO_ROOT/tests/fixtures/verifier_contract"
    CLAUDE_VERIFIER="$REPO_ROOT/configs/claude/agents/verifier.md"
    CURSOR_VERIFIER="$REPO_ROOT/configs/cursor/agents/verifier.md"
}

# ---- shipped definitions ---------------------------------------------------

@test "shipped: the Claude verifier satisfies every normative clause" {
    run python3 "$CHECK" "$CLAUDE_VERIFIER"
    assert_success
}

@test "shipped: the generated Cursor verifier satisfies the same contract" {
    run python3 "$CHECK" "$CURSOR_VERIFIER"
    assert_success
}

@test "shipped: Claude and Cursor verifier bodies are byte-identical (frontmatter aside)" {
    # The generator copies the body verbatim; only frontmatter may differ.
    run diff <(sed -n '/^---$/,/^---$/!p' "$CLAUDE_VERIFIER" | sed '1{/^$/d}') \
             <(sed -n '/^---$/,/^---$/!p' "$CURSOR_VERIFIER" | sed '1{/^$/d}')
    assert_success
}

# ---- contract rot: one fixture per failure mode ----------------------------

@test "adversarial: an inverted definition fails despite carrying both tokens" {
    run grep -qF 'CONFIRMED' "$FIXTURES/inverted.md"
    assert_success                      # the old token grep would have passed...
    run grep -qF 'REFUTED' "$FIXTURES/inverted.md"
    assert_success                      # ...on both counts
    run python3 "$CHECK" "$FIXTURES/inverted.md"
    assert_failure
    assert_output --partial 'mandates CONFIRMED unconditionally'
    assert_output --partial 'forbids the REFUTED verdict'
}

@test "rot: a definition naming both verdicts but stating no rules fails" {
    run python3 "$CHECK" "$FIXTURES/tokens_only.md"
    assert_failure
    assert_output --partial '[grounding]'
    assert_output --partial '[verdict]'
}

@test "rot: dropping the uncertain-defaults-to-REFUTED clause fails" {
    run python3 "$CHECK" "$FIXTURES/missing_uncertain.md"
    assert_failure
    assert_output --partial '[uncertain]'
}

@test "rot: a REFUTED verdict without reason and evidence fails" {
    run python3 "$CHECK" "$FIXTURES/missing_evidence.md"
    assert_failure
    assert_output --partial '[evidence]'
}

@test "semantic, not literal: a reworded but faithful definition passes" {
    # Guards the gate against degrading into a copy-match of the shipped text.
    run diff "$FIXTURES/reworded_valid.md" "$CLAUDE_VERIFIER"
    assert_failure                      # genuinely different wording
    run python3 "$CHECK" "$FIXTURES/reworded_valid.md"
    assert_success
}

# ---- CLI contract ----------------------------------------------------------

@test "cli: multiple files are all checked and one failure fails the run" {
    run python3 "$CHECK" "$CLAUDE_VERIFIER" "$FIXTURES/inverted.md"
    assert_failure
    assert_output --partial 'inverted.md'
}

@test "cli: --quiet suppresses the OK line but keeps violations" {
    run python3 "$CHECK" --quiet "$CLAUDE_VERIFIER"
    assert_success
    assert_output ""
}
