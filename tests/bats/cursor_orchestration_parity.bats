#!/usr/bin/env bats
# WS-2 (2026-07-11-cursor-feature-parity-design.md §3.2/§4): presence guard for
# the 6 CLAUDE.md items ported into configs/cursor/rules/orchestration.mdc.
# orchestration.mdc is hand-maintained (not generated), so future CLAUDE.md
# edits can silently desync it — this test fails loudly the moment any of the
# 6 ported tokens/sections goes missing again.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
RULE_FILE="$REPO_ROOT/configs/cursor/rules/orchestration.mdc"

@test "orchestration.mdc contains the Reference Index section with all 7 references" {
    run grep -c '^## Reference Index$' "$RULE_FILE"
    assert_output "1"
    for ref in parallel-agent.md orchestration.md git-platform.md layout.md \
               sub-agent-dispatch.md spec-artifact-discovery.md antipatterns.md; do
        grep -qF "~/.claude/references/$ref" "$RULE_FILE" || {
            echo "orchestration.mdc: missing reference $ref" >&2
            return 1
        }
    done
}

@test "orchestration.mdc contains the Graphify managed-tool paragraph" {
    grep -qF '**Graphify** is a managed *tool*, not a parallel-orchestration agent' "$RULE_FILE"
}

@test "orchestration.mdc contains the sync-skills CLI note" {
    grep -qF 'sync-skills' "$RULE_FILE"
    grep -qF 'daily skill dev workflow' "$RULE_FILE"
}

@test "orchestration.mdc contains the CONSIDER Parallel Agents For tier" {
    grep -qF '### CONSIDER Parallel Agents For' "$RULE_FILE"
}

@test "orchestration.mdc contains the code-audit auto-trigger thresholds" {
    grep -qF '### Auto-Triggered Rule' "$RULE_FILE"
    grep -qF '>500 lines, >10 functions, or >5' "$RULE_FILE"
}

@test "orchestration.mdc contains the token-conserve re-assert note" {
    grep -qF 're-asserts this mode if drift is noticed mid-session' "$RULE_FILE"
}
