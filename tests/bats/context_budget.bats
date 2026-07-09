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

@test "token-conserve section bullets are identical across all four guides" {
    # The same rules are stated in 4 always-loaded guides; this pins them
    # together so copies cannot drift. Compares only the '- '/continuation
    # bullet lines of the section (the /token-conserve re-assert line is
    # platform-specific and excluded).
    local ref="" cur f
    for f in "configs/claude/CLAUDE.md" "configs/gemini/GEMINI.md" \
             "AGENTS.md" "configs/cursor/rules/orchestration.mdc"; do
        cur=$(awk '/^## Token Economy \(always on\)$/{found=1; next}
                   found && /^## /{exit}
                   found && (/^- / || /^  [^ ]/)' "$REPO_ROOT/$f")
        [ -n "$cur" ] || { echo "$f: token-conserve section missing or empty" >&2; return 1; }
        if [ -z "$ref" ]; then ref="$cur"; reffile="$f"; continue; fi
        if [ "$cur" != "$ref" ]; then
            echo "$f token-conserve bullets differ from $reffile:" >&2
            diff <(echo "$ref") <(echo "$cur") >&2 || true
            return 1
        fi
    done
}

@test "skill frontmatter descriptions stay within per-session budget" {
    # Claude Code injects every skill's description at session start.
    # Budget covers the whole .skillshare/skills/ set.
    # Raised 18500 -> 19000 (2026-06-14) for the new issue-dev-auto skill:
    # per-skill frontmatter is already minimal (~250 chars each on average;
    # this skill ~290) and a
    # description has no read-on-demand alternative (it IS the always-loaded
    # triggering text), so a genuinely new skill must grow this budget. Keep
    # descriptions terse; if headroom runs low again, do a set-wide trim pass.
    # Raised 19000 -> 20000 (2026-06-17) for two genuinely-new skills with no
    # prior coverage: ci-audit-triggers + secure-comment-triggered-
    # workflow (GitHub-Actions trigger security). Descriptions kept terse.
    # Raised 20000 -> 21500 (2026-06-17) for the curated SkillClaw-evolve subset
    # (#366): 5 net-new skills (pr-merge-stacked, cli-help-before-
    # dependency-checks, test-pin-bug, shell-sete-silent-abort-
    # audit, ci-reproduce-failure) after dropping 2 overlapping/
    # niche candidates and folding errexit-safe-shell-counters into shell-sete.
    # Headroom is now thin (~200) — the next addition needs a set-wide trim pass.
    # Raised 21500 -> 22300 (2026-06-21) for two genuinely-new skills (#361):
    # issue-prep-auto + speckit-audit-tasks. Both were trimmed from
    # 717/595 -> 498/398 chars toward the ~290 norm first; the residual still
    # exceeded 21500, and the descriptions are the always-loaded triggering text
    # with no read-on-demand alternative. Headroom was ~160 — a set-wide trim
    # pass was overdue.
    # Lowered 22300 -> 21000 (2026-06-21): set-wide trim pass recovered ~1756
    # chars (total 22141 -> 20385); 25 skills trimmed toward the ~290 norm,
    # all trigger phrases preserved. New headroom: ~615 chars.
    # Raised 21000 -> 21500 (2026-06-21) for the genuinely-new `help` discovery
    # skill (spec 362): its description IS the always-loaded triggering text with
    # no read-on-demand alternative. Already trimmed to ~225 chars (well under the
    # ~290 norm) before this bump; the residual still cleared 21000 by only ~2.
    # Raised 21500 -> 22000 (2026-06-23) for the genuinely-new `smoke-manage`
    # skill (spec 363): the only smoke-test/E2E-coverage entry point, no prior
    # coverage to fold into. Frontmatter is 283 chars (under the ~290 norm); the
    # description is the always-loaded trigger text with no read-on-demand
    # alternative. Headroom after this is ~273 — the next addition needs a trim pass.
    # Raised 22000 -> 22300 (2026-06-28) for two genuinely-new entry-point skills
    # added on parallel branches and merged together: `graphify` (spec 364, 242
    # chars, the only knowledge-graph entry point) and `lifecycle` (spec 365, 205
    # chars, the only state-gated-lifecycle driver). Both branches independently
    # chose +300 from 22000; the merge confirmed 22300 still holds BOTH — the
    # measured total with both present is 22189. Both descriptions are always-loaded
    # trigger text with no read-on-demand alternative. Headroom is now only ~111 —
    # the next addition needs a trim pass first.
    # Raised 22300 -> 22600 (2026-06-30) for the genuinely-new `deploy-reconcile`
    # skill (spec 368, the only deploy-orphan-reconciliation entry point; no prior
    # coverage to fold in). Its description was trimmed to ~210 chars before the bump
    # (always-loaded trigger text, no read-on-demand alternative); measured total
    # with it present is 22490. Headroom after this is ~110 — next addition needs a trim.
    # Raised 22600 -> 22800 (2026-07-01) for the genuinely-new `ai-code-audit` skill
    # (spec 457, the only AI-defect/vibe-antipattern audit entry point; no prior
    # coverage to fold in). Trim pass done FIRST per the rule above: pr-smoke,
    # deploy-diagnose-drift, ci-audit-triggers trimmed ~190 chars total
    # (trigger phrases preserved); the new description was cut to ~300 chars and the
    # residual still exceeded 22600. Measured total with it present is 22679.
    # Headroom after this is ~124 — the next addition needs a set-wide trim pass first.
    # Lowered 22800 -> 22000 (2026-07-09): set-wide front-matter efficiency pass —
    # inline-normalized 39 block-scalar descriptions (Lever A, parsed value preserved)
    # + eval-guarded trims of 9 over-norm descriptions (Lever B) cut the total to
    # 21164. New cap leaves ~836 bytes (~3 skills) headroom — not near-zero, so a
    # genuinely-new skill still fits without an immediate bump. See
    # docs/superpowers/specs/2026-07-05-skill-frontmatter-efficiency-design.md.
    total=0
    for f in "$REPO_ROOT"/.skillshare/skills/*/SKILL.md; do
        # frontmatter = up to the second '---' line
        chars=$(awk '/^---$/{c++; next} c==1' "$f" | wc -c)
        total=$((total + chars))
    done
    if [ "$total" -gt 22000 ]; then
        echo "Skill frontmatter totals $total chars (budget: 22000)." >&2
        echo "Trim verbose descriptions; bodies are pay-per-use, frontmatter is not." >&2
        return 1
    fi
}

# spec 362 / FR-009 / SC-006: the compact command index injected into the
# always-loaded platform guides (GEMINI.md, AGENTS.md) must stay bounded as the
# catalog grows. The index is description-less (category headers + /name links)
# and links back to /help for detail; if this fails, the index has grown too
# large for always-loaded context — trim categories or drop to header-only links,
# do NOT raise the budget casually.
@test "injected command index stays within always-loaded budget" {
    local budget=3500 f size
    for f in "configs/gemini/GEMINI.md" "AGENTS.md"; do
        # Extract the block between the INDEX markers (inclusive).
        size=$(awk '/BEGIN COMMAND INDEX/{c=1} c{print} /END COMMAND INDEX/{c=0}' \
               "$REPO_ROOT/$f" | wc -c)
        if [ "$size" -eq 0 ]; then
            echo "$f: command index block not found (run generate_commands_doc.py --inject-guides)" >&2
            return 1
        fi
        if [ "$size" -gt "$budget" ]; then
            echo "$f command index is $size bytes (budget: $budget)." >&2
            echo "Trim the compact index; it is always-loaded every session." >&2
            return 1
        fi
    done
}
