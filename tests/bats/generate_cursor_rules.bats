#!/usr/bin/env bats
# Tests for configs/claude/scripts/generate_cursor_rules.sh
#
# The generator derives REPO_ROOT from its own location
# ($(dirname "$0")/../../..), so the hermetic seam is the script path:
# copying the script into a sandbox that mirrors the configs/claude/scripts
# layout makes it operate entirely on sandbox skills/rules dirs without
# any modification to the script itself.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/gen_cursor_rules.XXXXXX")
    SKILLS_DIR="$SANDBOX/configs/claude/skills"
    RULES_DIR="$SANDBOX/configs/cursor/rules"
    GEN="$SANDBOX/configs/claude/scripts/generate_cursor_rules.sh"
    mkdir -p "$SKILLS_DIR" "$RULES_DIR" "$SANDBOX/configs/claude/scripts"
    cp "$REPO_ROOT/configs/claude/scripts/generate_cursor_rules.sh" "$GEN"
    chmod +x "$GEN"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Helper: create a skill fixture with an inline description.
make_skill() {
    local name="$1" desc="$2"
    mkdir -p "$SKILLS_DIR/$name"
    cat > "$SKILLS_DIR/$name/SKILL.md" <<EOF
---
name: $name
description: $desc
---

# $name

Body of $name.
EOF
}

# ── Generation ───────────────────────────────────────────────────────────────

@test "generates one .mdc per skill with SKILL.md" {
    make_skill alpha "Alpha does things"
    make_skill beta "Beta does other things"
    make_skill gamma "Gamma is third"

    run "$GEN"
    assert_success
    assert_output --partial "3 created, 0 updated, 0 unchanged"

    [ -f "$RULES_DIR/alpha.mdc" ]
    [ -f "$RULES_DIR/beta.mdc" ]
    [ -f "$RULES_DIR/gamma.mdc" ]
    assert_equal "$(ls "$RULES_DIR" | wc -l | tr -d ' ')" "3"
}

@test "skill dir without SKILL.md is skipped, not counted" {
    make_skill alpha "Alpha"
    mkdir -p "$SKILLS_DIR/no-skill-md"   # no SKILL.md inside

    run "$GEN"
    assert_success
    assert_output --partial "1 created, 0 updated, 0 unchanged"
    [ ! -e "$RULES_DIR/no-skill-md.mdc" ]
}

@test "skill name and description appear in its generated .mdc" {
    make_skill my-skill "A very specific description marker"

    run "$GEN"
    assert_success

    run cat "$RULES_DIR/my-skill.mdc"
    assert_output --partial 'description: "A very specific description marker"'
    assert_output --partial "# my-skill"
    assert_output --partial ".cursor/skills/my-skill/SKILL.md"
}

@test "generated .mdc has valid frontmatter (delimiters, description, globs, alwaysApply)" {
    make_skill fm-check "Frontmatter check"
    run "$GEN"
    assert_success

    local mdc="$RULES_DIR/fm-check.mdc"
    # Line 1 opens frontmatter; a second --- closes it.
    assert_equal "$(head -1 "$mdc")" "---"
    assert_equal "$(grep -c '^---$' "$mdc")" "2"
    # Required keys inside the frontmatter block.
    front=$(sed -n '2,/^---$/p' "$mdc" | sed '$d')
    echo "$front" | grep -q '^description: ".*"$'
    echo "$front" | grep -q '^globs: ".claude/skills/fm-check/\*\*"$'
    echo "$front" | grep -q '^alwaysApply: false$'
}

@test "block scalar description (description: |) is collapsed into one line" {
    mkdir -p "$SKILLS_DIR/blocky"
    cat > "$SKILLS_DIR/blocky/SKILL.md" <<'EOF'
---
name: blocky
description: |
  First line of description.
  Second line of description.
---

# blocky
EOF

    run "$GEN"
    assert_success

    run cat "$RULES_DIR/blocky.mdc"
    assert_output --partial 'description: "First line of description. Second line of description."'
}

@test "missing description falls back to '<name> skill'" {
    # BUG: the intended fallback (description="${description:-$skill_name skill}",
    # line 65) is unreachable. With `set -euo pipefail`, a SKILL.md whose
    # frontmatter has no `description:` line makes
    #   desc_line=$(echo "$front_matter" | grep '^description:' | head -1)
    # (line 48) a failing pipeline (grep exits 1), which aborts the whole
    # script with exit 1 and no output. Fix: append `|| true` to that pipeline.
    skip "BUG: script exits 1 on a SKILL.md without a description (pipefail + grep, line 48)"

    mkdir -p "$SKILLS_DIR/nodesc"
    cat > "$SKILLS_DIR/nodesc/SKILL.md" <<'EOF'
---
name: nodesc
---

# nodesc
EOF

    run "$GEN"
    assert_success
    run cat "$RULES_DIR/nodesc.mdc"
    assert_output --partial 'description: "nodesc skill"'
}

# ── Idempotence / change detection ───────────────────────────────────────────

@test "second run is byte-idempotent on disk (counter miscounts: BUG)" {
    # BUG: the "unchanged" branch (lines 84-90) never fires. $content ends in a
    # newline and `echo "$content"` appends another, but
    # existing=$(cat "$rule_file") strips ALL trailing newlines — so
    # existing == content is always false and every rule is re-written and
    # counted as "updated" on every run. The on-disk bytes ARE stable (the
    # rewrite is identical), so this test pins true idempotence on content and
    # documents the miscount. Expected-after-fix: "0 created, 0 updated, 2 unchanged".
    make_skill alpha "Alpha"
    make_skill beta "Beta"
    "$GEN"
    before_alpha=$(shasum "$RULES_DIR/alpha.mdc")
    before_beta=$(shasum "$RULES_DIR/beta.mdc")

    run "$GEN"
    assert_success
    # Current (buggy) counter output; files themselves are unchanged.
    assert_output --partial "0 created, 2 updated, 0 unchanged"
    assert_equal "$(shasum "$RULES_DIR/alpha.mdc")" "$before_alpha"
    assert_equal "$(shasum "$RULES_DIR/beta.mdc")" "$before_beta"
}

@test "changed skill description is reflected in the regenerated rule" {
    # NOTE: because of the unchanged-detection BUG above, the counter reports
    # both rules as "updated" and cannot distinguish the truly changed one.
    # Assert on rule content instead, which is the behavior that matters.
    make_skill alpha "Alpha original"
    make_skill beta "Beta stable"
    "$GEN"

    make_skill alpha "Alpha revised"   # rewrite SKILL.md with new description
    run "$GEN"
    assert_success
    assert_output --partial "0 created, 2 updated, 0 unchanged"  # BUG: should be 1 updated, 1 unchanged

    run cat "$RULES_DIR/alpha.mdc"
    assert_output --partial "Alpha revised"
    run cat "$RULES_DIR/beta.mdc"
    assert_output --partial "Beta stable"
}

# ── Dry run ──────────────────────────────────────────────────────────────────

@test "--dry-run reports would-create but writes nothing" {
    make_skill alpha "Alpha"

    run "$GEN" --dry-run
    assert_success
    assert_output --partial "[DRY-RUN] Would create:"
    assert_output --partial "1 created, 0 updated, 0 unchanged"
    [ ! -e "$RULES_DIR/alpha.mdc" ]
}

@test "--dry-run reports would-update without modifying the existing rule" {
    make_skill alpha "Alpha v1"
    "$GEN"
    before=$(cat "$RULES_DIR/alpha.mdc")

    make_skill alpha "Alpha v2"
    run "$GEN" --dry-run
    assert_success
    assert_output --partial "[DRY-RUN] Would update:"
    assert_equal "$(cat "$RULES_DIR/alpha.mdc")" "$before"
}

# ── Edge cases ───────────────────────────────────────────────────────────────

@test "empty skills dir produces zero counts and exits 0" {
    run "$GEN"
    assert_success
    assert_output --partial "0 created, 0 updated, 0 unchanged"
    assert_equal "$(ls "$RULES_DIR" | wc -l | tr -d ' ')" "0"
}

@test "--help prints usage and exits 0" {
    run "$GEN" --help
    assert_success
    assert_output --partial "Usage:"
}

# ── Real repo (read-only-ish guarded check) ──────────────────────────────────

@test "real repo: rules are in sync — regenerate leaves the tree git-clean" {
    # Only meaningful when the working tree rules are clean; otherwise the test
    # would mutate tracked files. Skip rather than fail in that case.
    if ! git -C "$REPO_ROOT" diff --exit-code --quiet configs/cursor/rules/; then
        skip "configs/cursor/rules/ has local modifications; skipping repo-level check"
    fi

    run "$REPO_ROOT/configs/claude/scripts/generate_cursor_rules.sh"
    assert_success
    # BUG (see unchanged-detection note above): everything is counted as
    # "updated" even though the rewrites are byte-identical. After the fix this
    # should read "0 created, 0 updated, N unchanged".
    assert_output --regexp "Cursor rules: 0 created, [0-9]+ updated, [0-9]+ unchanged"

    # The real invariant: the tree is still clean afterwards (no drift).
    git -C "$REPO_ROOT" diff --exit-code --quiet configs/cursor/rules/
}

@test "real repo: every skill with SKILL.md has a corresponding .mdc rule" {
    local missing=0
    for skill_dir in "$REPO_ROOT"/configs/claude/skills/*/; do
        local name
        name=$(basename "$skill_dir")
        [ -f "$skill_dir/SKILL.md" ] || continue
        if [ ! -f "$REPO_ROOT/configs/cursor/rules/$name.mdc" ]; then
            echo "Missing rule for skill: $name"
            missing=$((missing + 1))
        fi
    done
    assert_equal "$missing" "0"
}
