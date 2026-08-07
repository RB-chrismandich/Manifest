#!/usr/bin/env bats
# Contract gate for the verifier role-agent (issue #689, ANTI-015).
#
# The gate this replaces grepped verifier.md for CONFIRMED and REFUTED, so an
# inverted definition passed. Three adversarial review rounds then walked through
# successive keyword heuristics, so the gate is now an allowlist: the body must
# equal the canonical body in configs/claude/config/verifier_contract.json,
# normalized — an added sentence fails whatever words it uses.
#
# Every fixture here is one demonstrated bypass of an earlier heuristic gate.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    CHECK="$REPO_ROOT/configs/claude/scripts/verifier_contract_check.py"
    FIXTURES="$REPO_ROOT/tests/fixtures/verifier_contract"
    CONTRACT="$REPO_ROOT/configs/claude/config/verifier_contract.json"
    CLAUDE_VERIFIER="$REPO_ROOT/configs/claude/agents/verifier.md"
    CURSOR_VERIFIER="$REPO_ROOT/configs/cursor/agents/verifier.md"
}

# ---- shipped definitions ---------------------------------------------------

@test "shipped: the Claude verifier matches the canonical contract" {
    run python3 "$CHECK" "$CLAUDE_VERIFIER"
    assert_success
}

@test "shipped: the generated Cursor verifier matches the same contract" {
    run python3 "$CHECK" "$CURSOR_VERIFIER"
    assert_success
}

@test "shipped: Claude and Cursor verifier bodies are identical (frontmatter aside)" {
    run diff <(sed -n '/^---$/,/^---$/!p' "$CLAUDE_VERIFIER" | sed '1{/^$/d}') \
             <(sed -n '/^---$/,/^---$/!p' "$CURSOR_VERIFIER" | sed '1{/^$/d}')
    assert_success
}

@test "shipped: the contract data itself carries no verdict bias" {
    run python3 "$CHECK" --contract "$CONTRACT" "$CLAUDE_VERIFIER"
    assert_success
}

# ---- inversion: the original #689 regression -------------------------------

@test "adversarial: an inverted definition fails despite carrying both tokens" {
    run grep -qF 'CONFIRMED' "$FIXTURES/inverted.md"
    assert_success                      # the old token grep would have passed...
    run grep -qF 'REFUTED' "$FIXTURES/inverted.md"
    assert_success                      # ...on both counts
    run python3 "$CHECK" "$FIXTURES/inverted.md"
    assert_failure
}

# ---- bypasses of the heuristic gates that preceded the allowlist -----------
# Each of these passed a keyword/co-occurrence gate while inverting the control.

@test "bypass: uncertainty clause revoked by the next sentence" {
    run python3 "$CHECK" "$FIXTURES/contradictory_uncertain.md"
    assert_failure
}

@test "bypass: CONFIRMED override appended after correct rules" {
    run python3 "$CHECK" "$FIXTURES/late_confirmed_override.md"
    assert_failure
}

@test "bypass: REFUTED suppressed by an imperative that names it" {
    run python3 "$CHECK" "$FIXTURES/suppress_refuted_append.md"
    assert_failure
    assert_output --partial 'non-canonical sentence'
}

@test "bypass: CONFIRMED gated on a hollow condition" {
    run python3 "$CHECK" "$FIXTURES/hollow_condition_append.md"
    assert_failure
    assert_output --partial 'non-canonical sentence'
}

@test "bypass: a token-free semantic override is rejected" {
    # Names no verdict at all: "deciding whether new prose is normative" is the
    # judgment the allowlist refuses to make, so the whole body is frozen.
    run python3 "$CHECK" "$FIXTURES/token_free_override.md"
    assert_failure
    assert_output --partial 'non-canonical sentence'
}

@test "bypass: uncertainty clause negated in place (avoid REFUTED)" {
    run python3 "$CHECK" "$FIXTURES/avoid_refuted.md"
    assert_failure
    assert_output --partial '[uncertain]'
}

@test "bypass: evidence requirement negated in place (no reason or evidence)" {
    run python3 "$CHECK" "$FIXTURES/negated_evidence.md"
    assert_failure
    assert_output --partial '[verdict]'
}

@test "bypass: a fullwidth-Unicode override is folded, then rejected" {
    # ASCII-only normalization deleted these characters outright, so the body
    # compared equal while a model still read the instruction (codex r4).
    run python3 "$CHECK" "$FIXTURES/fullwidth_override.md"
    assert_failure
    assert_output --partial 'non-canonical sentence'
}

@test "bypass: zero-width characters are a violation, never silently stripped" {
    run python3 "$CHECK" "$FIXTURES/zero_width_override.md"
    assert_failure
    assert_output --partial 'U+200B'
}

# ---- deletion ---------------------------------------------------------------

@test "rot: a definition naming both verdicts but stating no rules fails" {
    run python3 "$CHECK" "$FIXTURES/tokens_only.md"
    assert_failure
    assert_output --partial '[grounding]'
}

@test "rot: dropping the uncertain-defaults-to-REFUTED clause fails" {
    run python3 "$CHECK" "$FIXTURES/missing_uncertain.md"
    assert_failure
    assert_output --partial '[uncertain]'
}

@test "rot: a REFUTED verdict without reason and evidence fails" {
    run python3 "$CHECK" "$FIXTURES/missing_evidence.md"
    assert_failure
    assert_output --partial '[verdict]'
}

# ---- the allowlist cannot be laundered through its own data -----------------

@test "contract: an inverted contract file is rejected before any definition" {
    run python3 "$CHECK" --contract "$FIXTURES/inverted_contract.json" "$CLAUDE_VERIFIER"
    assert_failure
    assert_output --partial 'contract body is biased'
}

@test "contract: poisoning the body outside the clause list is rejected" {
    # Body and definition move in lockstep, so the comparison passes; only a
    # body-wide bias scan sees it (codex r4).
    run python3 "$CHECK" --contract "$FIXTURES/poisoned_body_contract.json" \
        "$FIXTURES/poisoned_body_definition.md"
    assert_failure
    assert_output --partial 'contract body is biased'
    assert_output --partial 'verdict outside every clause'
}

@test "contract: an unusable contract path is a usage error, never a pass" {
    run python3 "$CHECK" --contract "$FIXTURES/does-not-exist.json" "$CLAUDE_VERIFIER"
    [ "$status" -eq 2 ]
    assert_output --partial 'unusable contract'
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
