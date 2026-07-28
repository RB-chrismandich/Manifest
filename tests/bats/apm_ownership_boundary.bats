#!/usr/bin/env bats
# T009/T016 — FR-014/FR-027: exactly one writer per deployed domain.
#
# The migration's whole premise is that an area written by two pipelines under
# two ownership models drifts. This file is the instrument that proves how many
# LIVE writers a domain has, and it does so BEHAVIOURALLY — each candidate writer
# is actually run against an isolated HOME and the tree is inspected afterwards.
#
# A declarative list of "who writes what" would be the obvious cheaper design and
# it is the wrong one: an incomplete enumeration passes forever while seeing
# nothing, which is exactly the failure T009 calls out. So the enumeration is
# validated against a `find` over a really-deployed tree — if a writer touches a
# path outside its declared domain, the enumeration test fails rather than the
# path going unnoticed.
#
# Nothing here touches the real ~/.claude or the real registry.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_ownership.XXXXXX")"

    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude"

    # Fixture checkout: the source every writer deploys from.
    export MANIFEST_ROOT="$SANDBOX/repo"
    SRC="$MANIFEST_ROOT/.apm/skills"
    for s in alpha beta; do
        mkdir -p "$SRC/$s"
        printf -- '---\nname: %s\ndescription: d\n---\nbody\n' "$s" > "$SRC/$s/SKILL.md"
    done

    # Registry fixtures. Default: APM owns nothing (today's live state).
    REG_EMPTY="$SANDBOX/none.yml"
    printf 'domains: []\n' > "$REG_EMPTY"
    REG_SKILLS="$SANDBOX/skills.yml"
    printf 'domains:\n  - skills\n' > "$REG_SKILLS"
    export MANIFEST_APM_DOMAINS="$REG_EMPTY"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    print_success() { :; }
    print_warning() { :; }
    print_error() { :; }
    print_info() { :; }
    print_step() { :; }

    SYNC_SKILLS="$REPO_ROOT/configs/claude/scripts/sync-skills.sh"
    DOMAIN="$HOME/.claude/skills"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Did this writer put anything in the skills domain? Each probe starts from a
# clean domain so "wrote" cannot be inherited from a previous probe.
wrote_domain() { [[ -f "$DOMAIN/alpha/SKILL.md" ]]; }

probe_deploy_home_skills() {
    rm -rf "$DOMAIN"
    deploy_home_skills "$SRC" "$DOMAIN" > /dev/null 2>&1 || true
    wrote_domain
}

probe_sync_skills() {
    rm -rf "$DOMAIN"
    MANIFEST_ROOT="$MANIFEST_ROOT" MANIFEST_AGENT_ROSTER="$SANDBOX/absent.yml" \
        bash "$SYNC_SKILLS" > /dev/null 2>&1 || true
    wrote_domain
}

live_writer_count() {
    local n=0
    probe_deploy_home_skills && n=$((n + 1))
    probe_sync_skills && n=$((n + 1))
    echo "$n"
}

# --- the registry helper -----------------------------------------------------

@test "apm_owns_domain reads a block list" {
    MANIFEST_APM_DOMAINS="$REG_SKILLS" run apm_owns_domain skills
    assert_success
    MANIFEST_APM_DOMAINS="$REG_SKILLS" run apm_owns_domain config
    assert_failure
}

@test "apm_owns_domain reads an inline list" {
    printf 'domains: [skills, config]\n' > "$SANDBOX/inline.yml"
    MANIFEST_APM_DOMAINS="$SANDBOX/inline.yml" run apm_owns_domain config
    assert_success
    MANIFEST_APM_DOMAINS="$SANDBOX/inline.yml" run apm_owns_domain other
    assert_failure
}

@test "a missing registry means APM owns nothing, not everything" {
    # Fail-safe direction matters: treating an unreadable registry as
    # "APM owns everything" would gate every writer and brick bootstrap.
    MANIFEST_APM_DOMAINS="$SANDBOX/nope.yml" run apm_owns_domain skills
    assert_failure
}

# --- baseline (T009): the domain currently has two writers -------------------

@test "baseline: deploy_home_skills writes the skills domain" {
    export MANIFEST_APM_DOMAINS="$REG_EMPTY"
    run probe_deploy_home_skills
    assert_success
}

@test "baseline: sync-skills writes the skills domain" {
    export MANIFEST_APM_DOMAINS="$REG_EMPTY"
    run probe_sync_skills
    assert_success
}

@test "baseline: the skills domain has exactly two live writers" {
    export MANIFEST_APM_DOMAINS="$REG_EMPTY"
    run live_writer_count
    assert_output "2"
}

# --- the enumeration validates itself ----------------------------------------

@test "enumeration is complete: no writer touches a path outside its domain" {
    # The guard against a list that passes forever while seeing nothing. Deploy
    # for real, then diff the resulting tree against the enumerated domain root.
    export MANIFEST_APM_DOMAINS="$REG_EMPTY"
    rm -rf "$HOME/.claude"
    mkdir -p "$HOME/.claude"

    deploy_home_skills "$SRC" "$DOMAIN" > /dev/null 2>&1
    MANIFEST_ROOT="$MANIFEST_ROOT" MANIFEST_AGENT_ROSTER="$SANDBOX/absent.yml" \
        bash "$SYNC_SKILLS" > /dev/null 2>&1 || true

    # Everything either writer created under ~/.claude must sit inside the one
    # enumerated domain. A stray write elsewhere is an unenumerated domain.
    run bash -c "find '$HOME/.claude' -mindepth 1 -maxdepth 1 ! -name skills | wc -l | tr -d ' '"
    assert_output "0"
}

@test "the deployed tree is non-empty, so an empty-vs-empty comparison cannot pass" {
    export MANIFEST_APM_DOMAINS="$REG_EMPTY"
    rm -rf "$DOMAIN"
    deploy_home_skills "$SRC" "$DOMAIN" > /dev/null 2>&1
    run bash -c "find '$DOMAIN' -name SKILL.md | wc -l | tr -d ' '"
    assert_output "2"
}

# --- T016: after gating, the domain is unowned and safe to hand over ---------

@test "T016: with skills APM-owned, deploy_home_skills declines to write it" {
    export MANIFEST_APM_DOMAINS="$REG_SKILLS"
    run probe_deploy_home_skills
    assert_failure
}

@test "T016: with skills APM-owned, sync-skills declines to write it" {
    export MANIFEST_APM_DOMAINS="$REG_SKILLS"
    run probe_sync_skills
    assert_failure
}

@test "T016: with skills APM-owned, the domain has ZERO live writers" {
    # Not two, not one-plus-a-stale-CLI. This is the state Phase 2 exists to
    # reach, and it is only safe because T053 can hand the domain back.
    export MANIFEST_APM_DOMAINS="$REG_SKILLS"
    run live_writer_count
    assert_output "0"
}

@test "T016: gating skills does not gate an unrelated domain" {
    # A per-domain gate that silently became a global off-switch would pass the
    # zero-writer test above while breaking every other deploy.
    export MANIFEST_APM_DOMAINS="$REG_SKILLS"
    run apm_owns_domain config
    assert_failure
}

# --- the skip must be audible ------------------------------------------------

@test "sync-skills says it skipped, and names the replacement command" {
    # Silence reads as success. A contributor told nothing at all will assume
    # their edit deployed; one told only "skipped" has been handed a dead end.
    export MANIFEST_APM_DOMAINS="$REG_SKILLS"
    run env MANIFEST_ROOT="$MANIFEST_ROOT" MANIFEST_AGENT_ROSTER="$SANDBOX/absent.yml" \
        MANIFEST_APM_DOMAINS="$REG_SKILLS" bash "$SYNC_SKILLS"
    assert_output --partial "apm-dev-sync"
}
