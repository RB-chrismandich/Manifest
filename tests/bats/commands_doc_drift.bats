#!/usr/bin/env bats
# T008 — docs/COMMANDS.md drift-check exit codes (spec 362, US1, FR-004/SC-002).
# Exercises generate_commands_doc.py --check against a fixture skill add/remove.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
GEN="$REPO_ROOT/configs/claude/scripts/generate_commands_doc.py"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/commands_doc.XXXXXX")
    mkdir -p "$SANDBOX/skills"
    _skill() {
        mkdir -p "$SANDBOX/skills/$1"
        printf -- '---\nname: %s\ndescription: %s\n---\nbody\n' "$1" "$2" \
            > "$SANDBOX/skills/$1/SKILL.md"
    }
    _skill alpha "First skill."
    _skill beta "Second skill."

    cat > "$SANDBOX/categories.yml" <<'EOF'
categories:
  - {key: meta, label: "Meta", order: 1}
overrides:
  alpha: meta
  beta: meta
EOF
    printf 'services: {}\n' > "$SANDBOX/services.yml"

    export COMMAND_CATALOG_SKILLS_DIR="$SANDBOX/skills"
    export COMMAND_CATALOG_CATEGORIES="$SANDBOX/categories.yml"
    export COMMAND_CATALOG_SERVICES="$SANDBOX/services.yml"
    export COMMANDS_DOC_PATH="$SANDBOX/COMMANDS.md"
    # This suite drives a fixture catalog (alpha/beta); the always-loaded guide
    # indexes are repo files built from the REAL catalog, so skip the guide-index
    # half of --check here (empty override = no guide targets).
    export GUIDANCE_GUIDE_PATHS=""
    printf '# Commands\n\nIntro prose stays.\n' > "$COMMANDS_DOC_PATH"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "generate then --check is in sync (exit 0)" {
    run "$GEN"
    assert_success
    run "$GEN" --check
    assert_success
}

@test "adding a skill makes --check fail (exit 1) until regenerated" {
    "$GEN"
    mkdir -p "$SANDBOX/skills/gamma"
    printf -- '---\nname: gamma\ndescription: Third skill.\n---\nx\n' \
        > "$SANDBOX/skills/gamma/SKILL.md"
    run "$GEN" --check
    assert_failure 1
    run "$GEN"          # regenerate
    assert_success
    run "$GEN" --check
    assert_success
}

@test "preserves the hand-written prose outside the generated block" {
    "$GEN"
    run cat "$COMMANDS_DOC_PATH"
    assert_output --partial "Intro prose stays."
    assert_output --partial "/alpha"
}

@test "missing doc returns error exit 2" {
    rm -f "$COMMANDS_DOC_PATH"
    run "$GEN" --check
    assert_failure 2
}

@test "--check flags an out-of-date guide index and --inject-guides fixes it" {
    "$GEN"                                   # generate COMMANDS.md (in sync)
    local guide="$SANDBOX/GUIDE.md"
    printf '# Guide\n\nno index yet\n' > "$guide"
    GUIDANCE_GUIDE_PATHS="$guide" run "$GEN" --check
    assert_failure 1                         # guide index missing → drift
    GUIDANCE_GUIDE_PATHS="$guide" "$GEN" --inject-guides
    GUIDANCE_GUIDE_PATHS="$guide" run "$GEN" --check
    assert_success                           # now in sync
    run cat "$guide"
    assert_output --partial "/alpha"         # fixture catalog injected
}

@test "--help works before any dependency load" {
    run "$GEN" --help
    assert_success
    assert_output --partial "usage:"
}
