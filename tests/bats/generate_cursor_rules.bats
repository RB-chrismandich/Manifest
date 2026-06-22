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

@test "folded scalar description (description: >-) is collapsed into one line" {
    mkdir -p "$SKILLS_DIR/foldy"
    cat > "$SKILLS_DIR/foldy/SKILL.md" <<'EOF'
---
name: foldy
description: >-
  First line of description.
  Second line of description.
---

# foldy
EOF

    run "$GEN"
    assert_success

    run cat "$RULES_DIR/foldy.mdc"
    assert_output --partial 'description: "First line of description. Second line of description."'
}

@test "description containing double quotes is escaped to valid YAML frontmatter" {
    # Regression (PR #376): a raw " in the description used to terminate the
    # double-quoted YAML scalar early, leaving .mdc frontmatter invalid YAML
    # that Cursor could not load the rule from. The generator must escape
    # inner quotes as \" so the scalar stays balanced.
    make_skill quoted 'Use when logs are gated ("still in progress") or hard to read'

    run "$GEN"
    assert_success

    local mdc="$RULES_DIR/quoted.mdc"
    # Inner quotes are backslash-escaped (fixed-string match on the literal \").
    run grep -F 'description: "Use when logs are gated (\"still in progress\") or hard to read"' "$mdc"
    assert_success

    # And the frontmatter actually parses as YAML, when a parser is available.
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' 2>/dev/null; then
        front=$(sed -n '2,/^---$/p' "$mdc" | sed '$d')
        run python3 -c 'import sys,yaml; d=yaml.safe_load(sys.stdin.read()); assert isinstance(d,dict) and d.get("description"); print("yaml-ok")' <<<"$front"
        assert_success
        assert_output --partial "yaml-ok"
    fi
}

@test "missing description falls back to '<name> skill'" {
    # Regression: under `set -euo pipefail`, a SKILL.md with no `description:`
    # line made the grep pipelines exit 1 and aborted the script with no output,
    # so the intended fallback (description="${description:-$skill_name skill}")
    # was unreachable. The grep pipelines now tolerate no-match (`|| true`).
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

@test "second run is byte-idempotent on disk and counts rules as unchanged" {
    # Idempotence: a second run over already-current rules writes nothing and
    # counts both as unchanged. (The unchanged-detection compares the exact
    # bytes that would be written, including the trailing newline echo appends.)
    make_skill alpha "Alpha"
    make_skill beta "Beta"
    "$GEN"
    before_alpha=$(shasum "$RULES_DIR/alpha.mdc")
    before_beta=$(shasum "$RULES_DIR/beta.mdc")

    run "$GEN"
    assert_success
    # Both rules are byte-identical to the prior run, so unchanged-detection
    # must count them as unchanged (not re-written). The shasum below is the
    # real pin; the counter now reflects it.
    assert_output --partial "0 created, 0 updated, 2 unchanged"
    assert_equal "$(shasum "$RULES_DIR/alpha.mdc")" "$before_alpha"
    assert_equal "$(shasum "$RULES_DIR/beta.mdc")" "$before_beta"
}

@test "changed skill description is reflected in the regenerated rule" {
    # Only the rule whose SKILL.md changed is rewritten; the stable one is
    # counted as unchanged.
    make_skill alpha "Alpha original"
    make_skill beta "Beta stable"
    "$GEN"

    make_skill alpha "Alpha revised"   # rewrite SKILL.md with new description
    run "$GEN"
    assert_success
    assert_output --partial "0 created, 1 updated, 1 unchanged"

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

@test "--dry-run on an unchanged rule reports unchanged, not would-update" {
    # Regression: the unchanged-detection compared existing=$(cat file) (which
    # strips trailing newlines) against $content (which keeps one), so the
    # "unchanged" branch never fired and --dry-run falsely reported every
    # already-current rule as "Would update". A no-op run must be silent.
    make_skill alpha "Alpha stable"
    "$GEN"   # create alpha.mdc; nothing changes afterwards

    run "$GEN" --dry-run
    assert_success
    refute_output --partial "[DRY-RUN] Would update:"
    assert_output --partial "0 created, 0 updated, 1 unchanged"
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
    # Tree is already in sync, so every rule is counted as unchanged and
    # nothing is rewritten.
    assert_output --regexp "Cursor rules: 0 created, 0 updated, [0-9]+ unchanged"

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
