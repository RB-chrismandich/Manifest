#!/usr/bin/env bats
# Tests for the command discovery CLI (configs/claude/scripts/command_catalog.py).
# T006 adds the --help-before-dependency-checks path; T009 adds search/grouping/
# unavailable-marking and the truncation/--limit path.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
CATALOG="$REPO_ROOT/configs/claude/scripts/command_catalog.py"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/command_help.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# --- T006: --help must succeed BEFORE any config/skill-dir load -------------- #

@test "catalog --help exits 0 with no config present (clean env)" {
    # Point every dependency at a non-existent path: --help must still work
    # because help printing precedes dependency resolution.
    run env HOME="$SANDBOX" \
        COMMAND_CATALOG_SKILLS_DIR="$SANDBOX/nope" \
        COMMAND_CATALOG_CATEGORIES="$SANDBOX/nope.yml" \
        COMMAND_CATALOG_SERVICES="$SANDBOX/nope.yml" \
        "$CATALOG" --help
    assert_success
    assert_output --partial "usage:"
}

@test "catalog --help mentions --json and --platform" {
    run "$CATALOG" --help
    assert_success
    assert_output --partial "--json"
    assert_output --partial "--platform"
}

@test "catalog --json against the real skill library is valid JSON" {
    run "$CATALOG" --json
    assert_success
    echo "$output" | python3 -c "import sys,json; json.load(sys.stdin)"
}

# --- T009: discovery listing (search / grouping / unavailable / limit) ------ #

# Build a deterministic fixture skill library + config in $SANDBOX.
make_fixture() {
    mkdir -p "$SANDBOX/skills"
    _skill() { # name category description
        mkdir -p "$SANDBOX/skills/$1"
        printf -- '---\nname: %s\ndescription: %s\n---\nbody\n' "$1" "$3" \
            > "$SANDBOX/skills/$1/SKILL.md"
    }
    _skill branch-clean git-pr "Prune stale git branches."
    _skill repo-clean git-pr "Tidy up PRs and branches."
    _skill docs-all docs "Refresh all docs."
    _skill verify ci-cd "Run linters and tests."
    _skill skillclaw-promote skills "A service-gated tool."

    cat > "$SANDBOX/categories.yml" <<'EOF'
categories:
  - {key: git-pr, label: "Git & PRs", order: 1}
  - {key: docs, label: "Documentation", order: 2}
  - {key: ci-cd, label: "CI/CD", order: 3}
  - {key: skills, label: "Skills", order: 4}
overrides:
  branch-clean: git-pr
  repo-clean: git-pr
  docs-all: docs
  verify: ci-cd
  skillclaw-promote: skills
EOF
    cat > "$SANDBOX/services.yml" <<'EOF'
services:
  skillclaw:
    enabled: false
EOF
    export COMMAND_CATALOG_SKILLS_DIR="$SANDBOX/skills"
    export COMMAND_CATALOG_CATEGORIES="$SANDBOX/categories.yml"
    export COMMAND_CATALOG_SERVICES="$SANDBOX/services.yml"
}

@test "empty query lists commands grouped by category label" {
    make_fixture
    run "$CATALOG"
    assert_success
    assert_output --partial "Git & PRs"
    assert_output --partial "Documentation"
    assert_output --partial "/branch-clean"
}

@test "query ranks a name match first" {
    make_fixture
    run "$CATALOG" branch
    assert_success
    assert_line --index 0 --partial "branch-clean"
}

@test "--category restricts to one category" {
    make_fixture
    run "$CATALOG" --category docs
    assert_success
    assert_output --partial "/docs-all"
    refute_output --partial "/branch-clean"
}

@test "unavailable command hidden by default, shown with --all + reason" {
    make_fixture
    run "$CATALOG"
    refute_output --partial "skillclaw-promote"
    run "$CATALOG" --all
    assert_output --partial "skillclaw-promote"
    assert_output --partial "service disabled"
}

@test "no match prints an explicit message, not a misleading suggestion" {
    make_fixture
    run "$CATALOG" zzznotacommand
    assert_success
    assert_output --partial "No command matches"
}

@test "--limit truncates and prints an 'N more' footer" {
    make_fixture
    run "$CATALOG" --limit 2
    assert_success
    assert_output --partial "more"
}
