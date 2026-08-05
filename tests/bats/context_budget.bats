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
    # Lowered 7400 -> 7000 (2026-07-25) after a trim pass reclaimed 697 bytes
    # (7225 -> 6528): compacted the MCP routing list to one cue-preserving
    # paragraph, cut the duplicated second CLI example, condensed Plan
    # Management into its own README's pointer, and replaced the entry-point
    # gloss with `/help`. The old cap left ~55 bytes once the pilotfish
    # deploy-time pointer was added, so the next always-on rule would have
    # failed deploy_pilotfish.bats in the middle of unrelated work. Lowering
    # locks the gain in: ~470 bytes of source headroom, ~750 deployed.
    assert_budget "configs/claude/CLAUDE.md" 7000
}

@test "root CLAUDE.md stays within always-loaded budget" {
    assert_budget "CLAUDE.md" 12900
}

@test ".claude/CLAUDE.md stays within always-loaded budget" {
    assert_budget ".claude/CLAUDE.md" 3900
}

@test "configs/cursor/rules/orchestration.mdc stays within always-loaded budget" {
    # Cursor's alwaysApply rule (`~/.cursor/rules/orchestration.mdc`) is loaded
    # every session, same as the CLAUDE.md guides above. Baseline 12652 after
    # porting the WS-2 CLAUDE.md-parity items (Reference Index, Graphify note,
    # sync-skills note, CONSIDER tier, code-audit thresholds, /token-conserve
    # note); budget restores ~15% headroom (2026-07-11 cursor-feature-parity).
    assert_budget "configs/cursor/rules/orchestration.mdc" 14500
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

@test "no bundle's frontmatter exceeds the per-bundle session budget" {
    # Claude Code injects a skill's description at session start, so frontmatter
    # is always-loaded and rivalrous while bodies are pay-per-use.
    #
    # SCOPE IS PER BUNDLE, not the catalog. Before spec 674 every skill lived in
    # one flat ~/.claude/skills tree, so a catalog-wide sum WAS the session cost
    # and this test carried it (18500 -> 19000 -> 20000 -> 21500 -> 22300 ->
    # 22000 -> 25000 -> 29000 across a year of raises). After the cutover a
    # session loads the bundles the user installed, so the catalog sum stopped
    # being the session budget. That was recognised at the time -- see "the
    # catalog-wide sum is a SECONDARY guard" below, whose comment says treating
    # it as the session budget "is what made the old comment wrong" -- but this
    # test was left measuring the retired thing.
    #
    # Two tests then guarded one number with contradictory meanings, and because
    # this one summed the RAW frontmatter block (keys, newlines and all) against
    # the same 29000 cap the secondary applies to values only, it ran ~3740
    # chars stricter than anyone chose. Measured 2026-08-05: raw-block catalog
    # 28878 vs values-only 25135. It reported 4 chars of headroom and cost a real
    # trim of three skills' trigger phrases before the duplication was spotted;
    # those trims have been reverted.
    #
    # Reconciled here: raw-block accounting (the better proxy -- the harness
    # loads keys, not just values) applied to the scope that is actually loaded.
    # Cap 7000 against a measured max of 5238 (manifest-code-quality, 22 skills,
    # 2026-08-05) leaves ~1760, about 7 average skills, for the largest bundle.
    # This supersedes the separate values-only per-bundle cap that sat at 6000.
    #
    # Reads plugins/ (the source of truth), not .apm/skills -- that mirror is a
    # gitignored build artifact and is EMPTY in a fresh checkout, which made the
    # old form of this test pass vacuously there.
    cd "$REPO_ROOT"
    run python3 - <<'BUDGET'
import pathlib, re, sys

CAP = 7000
over, sizes = [], []
for bundle in sorted(p for p in pathlib.Path("plugins").iterdir() if p.is_dir()):
    total = 0
    for f in bundle.glob("skills/*/SKILL.md"):
        m = re.match(r"^---\n(.*?)\n---\n", f.read_text(encoding="utf-8"), re.S)
        if m:
            total += len(m.group(1)) + 1  # + the trailing newline
    if total:
        sizes.append((total, bundle.name))
    if total > CAP:
        over.append(f"{bundle.name}={total}")

if not sizes:
    print("no bundle frontmatter found under plugins/ — the gate would pass vacuously")
    sys.exit(1)

sizes.sort(reverse=True)
print(f"largest bundle: {sizes[0][1]}={sizes[0][0]} (cap {CAP})")
if over:
    print("OVER CAP:", ", ".join(over))
    print("Trim that bundle's verbose descriptions, or split the bundle.")
sys.exit(1 if over else 0)
BUDGET
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}

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

# --- per-bundle caps (T3.7, spec 674) --------------------------------------
#
# Post-cutover the always-on cost a user pays is the sum over the bundles they
# INSTALLED, not the whole catalog. A single total cannot express that: someone
# with two bundles and someone with nine both pass or both fail together.
#
# What this measures is REPO BYTES. The invariant it is a proxy for -- the
# session's actual listing budget -- is a property of the user's install set,
# which no bats test can see. That check belongs in /env-check as a runtime
# observation. This repo has already been burned once by a budget test
# measuring the wrong universe, so the limitation is stated rather than implied.

@test "the catalog-wide sum is a SECONDARY guard, not the session budget" {
    # Demoted deliberately. It no longer claims to guard what a session loads --
    # after the cutover nobody loads the whole catalog at once, and treating this
    # number as the session budget is what made the old comment wrong.
    cd "$REPO_ROOT"
    run python3 - <<'PY'
import pathlib, sys, yaml
CAP = 29000
total = 0
for f in pathlib.Path("plugins").glob("*/skills/*/SKILL.md"):
    t = f.read_text(encoding="utf-8")
    if t.startswith("---"):
        d = yaml.safe_load(t.split("---", 2)[1]) or {}
        total += len(str(d.get("name", ""))) + len(str(d.get("description", "")))
print(f"total={total}")
sys.exit(1 if total > CAP else 0)
PY
    [ "$status" -eq 0 ] || { echo "$output"; false; }
}
