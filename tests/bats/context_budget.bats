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
    # Deployed to ~/.claude/CLAUDE.md: loaded in EVERY session on EVERY project.
    # Re-based from 6600 after the intentional "Token Economy (always on)"
    # baseline section landed (file at 6448; restores ~15% headroom).
    assert_budget "configs/claude/CLAUDE.md" 7400
}

@test "root CLAUDE.md stays within always-loaded budget" {
    assert_budget "CLAUDE.md" 12900
}

@test ".claude/CLAUDE.md stays within always-loaded budget" {
    assert_budget ".claude/CLAUDE.md" 3900
}

@test "token-economy section bullets are identical across all four guides" {
    # The same rules are stated in 4 always-loaded guides; this pins them
    # together so copies cannot drift. Compares only the '- '/continuation
    # bullet lines of the section (the /token-economy re-assert line is
    # platform-specific and excluded).
    local ref="" cur f
    for f in "configs/claude/CLAUDE.md" "configs/gemini/GEMINI.md" \
             "AGENTS.md" "configs/cursor/rules/orchestration.mdc"; do
        cur=$(awk '/^## Token Economy \(always on\)$/{found=1; next}
                   found && /^## /{exit}
                   found && (/^- / || /^  [^ ]/)' "$REPO_ROOT/$f")
        [ -n "$cur" ] || { echo "$f: token-economy section missing or empty" >&2; return 1; }
        if [ -z "$ref" ]; then ref="$cur"; reffile="$f"; continue; fi
        if [ "$cur" != "$ref" ]; then
            echo "$f token-economy bullets differ from $reffile:" >&2
            diff <(echo "$ref") <(echo "$cur") >&2 || true
            return 1
        fi
    done
}

@test "skill frontmatter descriptions stay within per-session budget" {
    # Claude Code injects every skill's description at session start.
    # Budget covers the whole .skillshare/skills/ set.
    # Raised 18500 -> 19000 (2026-06-14) for the new auto-issue-dev skill:
    # per-skill frontmatter is already minimal (~250 chars each on average;
    # this skill ~290) and a
    # description has no read-on-demand alternative (it IS the always-loaded
    # triggering text), so a genuinely new skill must grow this budget. Keep
    # descriptions terse; if headroom runs low again, do a set-wide trim pass.
    # Raised 19000 -> 20000 (2026-06-17) for two genuinely-new skills with no
    # prior coverage: ci-workflow-trigger-security + secure-comment-triggered-
    # workflow (GitHub-Actions trigger security). Descriptions kept terse.
    total=0
    for f in "$REPO_ROOT"/.skillshare/skills/*/SKILL.md; do
        # frontmatter = up to the second '---' line
        chars=$(awk '/^---$/{c++; next} c==1' "$f" | wc -c)
        total=$((total + chars))
    done
    if [ "$total" -gt 20000 ]; then
        echo "Skill frontmatter totals $total chars (budget: 20000)." >&2
        echo "Trim verbose descriptions; bodies are pay-per-use, frontmatter is not." >&2
        return 1
    fi
}
