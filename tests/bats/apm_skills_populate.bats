#!/usr/bin/env bats
# The bootstrap side of an APM-owned `skills` domain.
#
# SC-006 gated the domain so deploy_home_skills stands down, but bootstrap kept
# asserting the deployed SKILL.md files as its OWN required files — so a deploy
# that correctly stood down exited 1 with three "Missing:" errors naming a tree
# it no longer writes, and nothing in bootstrap populated that tree. Both halves
# are covered here:
#
#   verify_installation()      — reports, never blames the wrong pipeline
#   populate_apm_owned_skills() — writes ONLY an empty apm-owned domain
#
# Everything runs against a sandbox HOME and a fabricated repo root; nothing
# touches the real ~/.claude or the real checkout.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/apm_skills_populate.XXXXXX")"
    export HOME="$SANDBOX/home"
    export TARGET_DIR="$HOME/.claude"
    export CURSOR_TARGET_DIR="$HOME/.cursor"
    export GEMINI_TARGET_DIR="$HOME/.gemini"
    export CODEX_TARGET_DIR="$HOME/.codex"
    export ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export MANIFEST_STATE_DIR="$HOME/.manifest"
    export MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/orchestration/outputs"
    export MANIFEST_TMP_DIR="$MANIFEST_STATE_DIR/tmp"
    export ENABLE_CLAUDE=true ENABLE_GEMINI=true ENABLE_CURSOR=true \
        ENABLE_CODEX=true ENABLE_ANTIGRAVITY=false ENABLE_GH=false ENABLE_GLAB=false
    mkdir -p "$HOME"

    # Ownership registry fixture — the ONLY ownership signal these tests vary.
    export MANIFEST_APM_DOMAINS="$SANDBOX/domains.yml"
    ungate_skills

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

gate_skills() { printf 'domains:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"; }
ungate_skills() { printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"; }
retire_skills() { printf 'domains:\n  - skills\nretired:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"; }

# Everything verify_installation checks EXCEPT the skill files, so a non-zero
# exit can only come from the skills assertions under test.
fabricate_verified_install() {
    mkdir -p "$TARGET_DIR/scripts" "$TARGET_DIR/config" "$CURSOR_TARGET_DIR/rules" \
        "$GEMINI_TARGET_DIR" "$CODEX_TARGET_DIR"
    touch "$TARGET_DIR/scripts/parallel_agent.py" "$TARGET_DIR/scripts/git_platform.sh" \
        "$TARGET_DIR/scripts/git_ops.sh" "$TARGET_DIR/config/command_config.yml" \
        "$TARGET_DIR/config/mcp_servers.yml" "$TARGET_DIR/config/validation_criteria.yml" \
        "$TARGET_DIR/config/services.yml" "$TARGET_DIR/CLAUDE.md" \
        "$CURSOR_TARGET_DIR/rules/orchestration.mdc" "$CURSOR_TARGET_DIR/mcp.json" \
        "$CURSOR_TARGET_DIR/hooks.json" "$GEMINI_TARGET_DIR/GEMINI.md" \
        "$CODEX_TARGET_DIR/AGENTS.md"
    mkdir -p "$MANIFEST_OUTPUT_DIR" "$MANIFEST_TMP_DIR" "$MANIFEST_STATE_DIR/claude" \
        "$MANIFEST_STATE_DIR/gemini" "$MANIFEST_STATE_DIR/cursor" \
        "$MANIFEST_STATE_DIR/codex/sessions" "$MANIFEST_STATE_DIR/antigravity"
}

deploy_skill_files() {
    local d
    for d in "$CURSOR_TARGET_DIR" "$GEMINI_TARGET_DIR" "$CODEX_TARGET_DIR"; do
        mkdir -p "$d/skills/code-audit"
        printf -- '---\nname: code-audit\n---\n' > "$d/skills/code-audit/SKILL.md"
    done
}

# --- verify_installation ------------------------------------------------------

@test "an apm-owned domain with no skills is a HARD error (T1.7, spec 674)" {
    # This assertion was INVERTED by T1.7, deliberately. It used to require a
    # warning and exit 0, which meant a user with no skills at all saw
    # "Deployment verified" -- a total failure reported as success. Verifying a
    # deployment must not pass when the deployment is empty, however legitimate
    # the reason the writer stood down.
    gate_skills
    fabricate_verified_install

    run verify_installation
    assert_failure
    assert_output --partial "Missing (apm-owned domain)"
    assert_output --partial "apm-dev-sync"
}

@test "a RETIRED domain with no skills is correct, and says nothing at all" {
    # The post-cutover target state: the plugin bundles serve the catalog and
    # ~/.claude/skills is EMPTY on purpose. T1.7's hard error landed in Phase 1,
    # before `retired:` existed, so leaving it unconditional would print
    # "Missing" 108 times and fail verification on every correct machine --
    # the mirror image of the false green T1.7 removed.
    retire_skills
    fabricate_verified_install

    run verify_installation
    assert_success
    refute_output --partial "Missing (apm-owned domain)"
    refute_output --partial "has not populated it"
}

@test "an unowned domain with no skills is still a hard bootstrap error" {
    # Legacy pipeline: deploy_home_skills IS the writer, so missing skills mean
    # bootstrap itself failed and must say so.
    ungate_skills
    fabricate_verified_install

    run verify_installation
    assert_failure
    assert_output --partial "Missing: .cursor/skills/code-audit/SKILL.md"
    refute_output --partial "apm-owned domain"
}

@test "deployed skills verify clean under either owner" {
    fabricate_verified_install
    deploy_skill_files

    gate_skills
    run verify_installation
    assert_success
    refute_output --partial "Missing (apm-owned domain)"

    ungate_skills
    run verify_installation
    assert_success
}

@test "the Antigravity skill file is only required when Antigravity is enabled" {
    gate_skills
    fabricate_verified_install
    deploy_skill_files

    export ENABLE_ANTIGRAVITY=true
    run verify_installation
    assert_output --partial "Missing (apm-owned domain): .antigravity/skills/code-audit/SKILL.md"

    export ENABLE_ANTIGRAVITY=false
    run verify_installation
    refute_output --partial ".antigravity/skills"
}

# --- populate_apm_owned_skills: DELETED by spec 674 Phase 5 (T5.3) -----------
#
# The function and its 8 cases are gone with their subject. Its premise was that
# apm owns ~/.claude/skills and bootstrap must never leave that tree empty;
# post-cutover EMPTY IS THE GOAL. The verify_installation cases above are kept
# and now assert the three-state behaviour, including that a RETIRED domain with
# no skills is correct and silent.

@test "populate_apm_owned_skills is gone, and nothing still calls it" {
    # Retired deliberately rather than by attrition: a surviving call site would
    # refill ~/.claude/skills on the next bootstrap and double-load all 108
    # skills against their plugin twins, with no error anywhere.
    run bash -c "grep -rn 'populate_apm_owned_skills' \
        '$REPO_ROOT/bootstrap.sh' '$REPO_ROOT/bootstrap/lib/' 2>/dev/null \
        | grep -v 'deleted here by spec 674' | wc -l | tr -d ' '"
    assert_output "0"
}
