#!/usr/bin/env bats
# Token-economy regression guard: files in this list are auto-loaded into agent
# context every session (Claude Code loads all three CLAUDE.md files; the
# platform guides load in their respective CLIs). Budgets are bytes with ~15%
# headroom over the 2026-06-12 trim (PR: token-economy-context-trim).
#
# If a test fails: prefer moving content to a read-on-demand reference
# (configs/claude/references/, docs/) over raising the budget. Raise a budget
# only with a rationale in the commit message.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"

assert_budget() {
    local file="$1" budget="$2"
    local size
    size=$(wc -c < "$REPO_ROOT/$file")
    if [ "$size" -gt "$budget" ]; then
        echo "$file is $size bytes (budget: $budget)." >&2
        echo "Move content to a read-on-demand reference instead of growing always-loaded context." >&2
        return 1
    fi
}

@test "configs/claude/CLAUDE.md stays within always-loaded budget" {
    # Deployed to ~/.claude/CLAUDE.md: loaded in EVERY session on EVERY project
    assert_budget "configs/claude/CLAUDE.md" 6600
}

@test "root CLAUDE.md stays within always-loaded budget" {
    assert_budget "CLAUDE.md" 12900
}

@test ".claude/CLAUDE.md stays within always-loaded budget" {
    assert_budget ".claude/CLAUDE.md" 3900
}

@test "skill frontmatter descriptions stay within per-session budget" {
    # Claude Code injects every skill's description at session start.
    # Budget covers the whole .skillshare/skills/ set (~16k chars as of trim).
    total=0
    for f in "$REPO_ROOT"/.skillshare/skills/*/SKILL.md; do
        # frontmatter = up to the second '---' line
        chars=$(awk '/^---$/{c++; next} c==1' "$f" | wc -c)
        total=$((total + chars))
    done
    if [ "$total" -gt 18500 ]; then
        echo "Skill frontmatter totals $total chars (budget: 18500)." >&2
        echo "Trim verbose descriptions; bodies are pay-per-use, frontmatter is not." >&2
        return 1
    fi
}
