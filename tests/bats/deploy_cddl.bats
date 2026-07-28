#!/usr/bin/env bats
# Deployment-safety tests for CDDL role prompts (feature 482, T040; SC-008/FR-014).
# The deploy stream is bootstrap/lib/deploy.sh's plain rsync of configs/claude/
# (prompts/ included, /agents excluded) — these tests pin that contract and the
# reconcile-based retirement path.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
DEPLOY_SH="$REPO_ROOT/bootstrap/lib/deploy.sh"
PROMPTS_SRC="$REPO_ROOT/configs/claude/prompts/cddl"
# Mirrors the deploy.sh rsync invocations (both copy paths); the static test
# below fails if deploy.sh's flags drift from this mirror.
RSYNC_EXCLUDES=(--exclude '/skills' --exclude '/agents' --exclude '/references/pilotfish-delegation.md')

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/deploy_cddl.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "repo ships the CDDL role prompts with valid frontmatter" {
    for f in developer developer-reviewer implementer qa-critic arch-critic; do
        [ -f "$PROMPTS_SRC/$f.md" ]
        head -1 "$PROMPTS_SRC/$f.md" | grep -q '^---$'
        grep -q "^name: $f$" "$PROMPTS_SRC/$f.md"
        grep -q '^description: ' "$PROMPTS_SRC/$f.md"
        grep -qE '^model: (haiku|sonnet|opus)$' "$PROMPTS_SRC/$f.md"
    done
}

@test "role prompt filenames are disjoint from the six pilotfish agent names" {
    for f in scout Explore mech-executor executor verifier security-executor; do
        [ ! -e "$PROMPTS_SRC/$f.md" ]
    done
}

@test "deploy.sh rsync excludes /agents and does NOT exclude /prompts (both copy paths)" {
    # Two rsync copy paths: merge (--ignore-existing) and replace.
    run grep -cE "rsync -a.*--exclude '/agents'" "$DEPLOY_SH"
    assert_output "2"
    run grep -cE "rsync -a.*--exclude '/prompts'" "$DEPLOY_SH"
    assert_output "0"
}

@test "deploy places role prompts; agents registry byte-identical (SC-008)" {
    src="$SANDBOX/src"
    target="$SANDBOX/home/.claude"
    mkdir -p "$src/prompts/cddl" "$src/agents" "$target/agents"
    cp "$PROMPTS_SRC/"*.md "$src/prompts/cddl/"
    echo "repo agent" > "$src/agents/scout.md"          # excluded from stream
    echo "user agent" > "$target/agents/my-agent.md"    # pre-existing user file
    before=$(find "$target/agents" -type f | sort | xargs shasum)

    rsync -a "${RSYNC_EXCLUDES[@]}" "$src/" "$target/"

    [ -f "$target/prompts/cddl/developer.md" ]
    [ -f "$target/prompts/cddl/developer-reviewer.md" ]
    [ -f "$target/prompts/cddl/implementer.md" ]
    [ -f "$target/prompts/cddl/qa-critic.md" ]
    [ -f "$target/prompts/cddl/arch-critic.md" ]
    after=$(find "$target/agents" -type f | sort | xargs shasum)
    assert_equal "$after" "$before"                     # zero registry writes
    [ ! -e "$target/agents/scout.md" ]
}

@test "redeploy preserves operator-added files and reconverges role files (FR-014)" {
    src="$SANDBOX/src"
    target="$SANDBOX/home/.claude"
    mkdir -p "$src/prompts/cddl" "$target"
    cp "$PROMPTS_SRC/"*.md "$src/prompts/cddl/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$src/" "$target/"

    echo "my custom prompt" > "$target/prompts/cddl/my-custom.md"  # operator file
    echo "local drift" > "$target/prompts/cddl/qa-critic.md"       # hand-edited

    rsync -a "${RSYNC_EXCLUDES[@]}" "$src/" "$target/"             # replace-path redeploy

    assert_equal "$(cat "$target/prompts/cddl/my-custom.md")" "my custom prompt"
    run diff "$target/prompts/cddl/qa-critic.md" "$src/prompts/cddl/qa-critic.md"
    assert_success                                                  # reconverged
}

@test "retirement: reconcile flags orphaned prompts/cddl for removal, and only it" {
    home_base="$SANDBOX/home"
    project="$SANDBOX/project"
    mkdir -p "$home_base/.claude/prompts/cddl" "$home_base/.claude/prompts/keepme" \
             "$project/configs/claude/prompts/keepme" "$project/.apm/skills"
    echo x > "$home_base/.claude/prompts/cddl/implementer.md"
    echo y > "$home_base/.claude/prompts/keepme/note.md"
    echo y > "$project/configs/claude/prompts/keepme/note.md"

    run python3 "$REPO_ROOT/configs/claude/scripts/reconcile_core.py" \
        --home "$home_base" --project "$project" --format json
    assert_success
    assert_output --partial '"display_path": "~/.claude/prompts/cddl"'
    assert_output --partial '"verdict": "REMOVE"'
    # the sourced prompts/keepme unit is reconciled — never listed as an orphan
    refute_output --partial "prompts/keepme"
}

@test "reconcile keeps prompts/cddl while the feature is in the project source" {
    home_base="$SANDBOX/home"
    project="$SANDBOX/project"
    mkdir -p "$home_base/.claude/prompts/cddl" \
             "$project/configs/claude/prompts/cddl" "$project/.apm/skills"
    echo x > "$home_base/.claude/prompts/cddl/implementer.md"
    echo x > "$project/configs/claude/prompts/cddl/implementer.md"

    run python3 "$REPO_ROOT/configs/claude/scripts/reconcile_core.py" \
        --home "$home_base" --project "$project" --format json
    assert_success
    refute_output --partial "prompts/cddl"
}
