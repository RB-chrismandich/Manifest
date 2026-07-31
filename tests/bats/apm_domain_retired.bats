#!/usr/bin/env bats
# T2.1 + T2.2 (spec 674) — the third ownership state, and the three writers.
#
# The registry was strictly two-state: listed under `domains:` meant APM writes,
# and UNLISTED MEANT THE LEGACY WRITER WRITES. So handing `skills` to plugins by
# removing it from `domains:` would not stand a writer down -- it would RE-ARM
# two of them, refill ~/.claude/skills, and double-load all 108 skills against
# their plugin twins with no dedup and no error.
#
# These tests are the disarm proof. Each writer is checked in BOTH directions,
# because a gate that always declines is indistinguishable from a working one
# until the day someone needs it to act.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/retired.XXXXXX")"
    RETIRED="$SANDBOX/retired.yml"
    NORMAL="$SANDBOX/normal.yml"
    printf 'domains: []\nretired:\n  - skills\n' > "$RETIRED"
    printf 'domains: []\nretired: []\n' > "$NORMAL"
    mkdir -p "$SANDBOX/src/demo" "$SANDBOX/dest"
    echo body > "$SANDBOX/src/demo/SKILL.md"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

# --- the state itself ------------------------------------------------------

@test "domain_retired reads the retired: list" {
    source "$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh"
    MANIFEST_APM_DOMAINS="$RETIRED" domain_retired skills
}

@test "domain_retired is false for a domain that is merely unlisted" {
    source "$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh"
    run env MANIFEST_APM_DOMAINS="$NORMAL" bash -c "
        source '$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh'; domain_retired skills"
    assert_failure
}

@test "retired and owned are independent states" {
    printf 'domains:\n  - skills\nretired:\n  - other\n' > "$SANDBOX/both.yml"
    run env MANIFEST_APM_DOMAINS="$SANDBOX/both.yml" bash -c "
        source '$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh'
        apm_owns_domain skills && echo OWNS
        domain_retired other && echo RETIRED
        domain_retired skills || echo SKILLS_NOT_RETIRED"
    assert_output --partial "OWNS"
    assert_output --partial "RETIRED"
    assert_output --partial "SKILLS_NOT_RETIRED"
}

# --- writer (a): deploy_home_skills ---------------------------------------

@test "deploy_home_skills writes nothing when the domain is retired" {
    run bash -c "
        print_info() { :; }; print_error() { :; }; print_success() { :; }; print_warning() { :; }
        source '$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh'
        source '$REPO_ROOT/bootstrap/lib/skill_prune.sh'
        export MANIFEST_APM_DOMAINS='$RETIRED'
        source '$REPO_ROOT/bootstrap/lib/common.sh' 2>/dev/null
        deploy_home_skills '$SANDBOX/src' '$SANDBOX/dest' skills >/dev/null 2>&1
        find '$SANDBOX/dest' -name SKILL.md | wc -l | tr -d ' '"
    assert_output --partial "0"
}

@test "deploy_home_skills still writes when the domain is NOT retired" {
    # The direction that proves the gate is a gate and not a permanent decline.
    run bash -c "
        print_info() { :; }; print_error() { :; }; print_success() { :; }; print_warning() { :; }
        source '$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh'
        source '$REPO_ROOT/bootstrap/lib/skill_prune.sh'
        export MANIFEST_APM_DOMAINS='$NORMAL'
        source '$REPO_ROOT/bootstrap/lib/common.sh' 2>/dev/null
        deploy_home_skills '$SANDBOX/src' '$SANDBOX/dest' skills >/dev/null 2>&1
        find '$SANDBOX/dest' -name SKILL.md | wc -l | tr -d ' '"
    assert_output --partial "1"
}

# --- writer (b): sync-skills ----------------------------------------------

@test "sync-skills declines a retired domain and names the replacement" {
    run env MANIFEST_ROOT="$REPO_ROOT" MANIFEST_APM_DOMAINS="$RETIRED" \
        bash "$REPO_ROOT/configs/claude/scripts/sync-skills.sh"
    assert_output --partial "retired from both pipelines"
    assert_output --partial "claude plugin update"
}

# --- writer (c): apm-dev-sync — RETIRED by spec 674 Phase 5 (T5.4) ----------
#
# The script is gone with its subject, so its two cases go with it. The disarm
# they proved is now unconditional: there is no apm-dev-sync to refuse.

@test "apm-dev-sync is gone, and bootstrap no longer installs it" {
    # A stale copy on PATH is worse than none: it would run, report success, and
    # sync a tree nothing reads any more.
    [ ! -f "$REPO_ROOT/configs/claude/scripts/apm_dev_sync.sh" ]
    run grep -c 'local/bin/apm-dev-sync"$' "$REPO_ROOT/bootstrap/lib/deploy.sh"
    [ "$output" -eq 1 ]  # the `rm -f` prune only
}

# --- the shipped registry --------------------------------------------------

@test "the shipped registry declares retired: with skills activated" {
    # Activated 2026-07-30 once ~/.manifest/skills existed and all four siblings
    # resolved into it. Activating before that would have left every assistant
    # with nothing: each writer correctly declines, nothing had taken over yet.
    run grep -A1 -E '^retired:' "$REPO_ROOT/configs/claude/config/apm_domains.yml"
    assert_success
}

# --- T2.4: the mandatory domain argument -----------------------------------

@test "deploy_home_skills is silently a no-op for <root>/skills without the domain arg" {
    # The trap: the domain defaults to basename("$dest"), which stays "skills"
    # even after the tree moves to ~/.manifest/skills -- and apm owns "skills".
    # Without an explicit third argument the new harness tree is NEVER written,
    # and every sibling gets a dangling symlink with no error anywhere.
    printf 'domains:\n  - skills\nretired: []\n' > "$SANDBOX/apmowned.yml"
    mkdir -p "$SANDBOX/manifest/skills"
    run bash -c "
        print_info() { :; }; print_error() { :; }; print_success() { :; }; print_warning() { :; }
        source '$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh'
        source '$REPO_ROOT/bootstrap/lib/skill_prune.sh'
        export MANIFEST_APM_DOMAINS='$SANDBOX/apmowned.yml'
        source '$REPO_ROOT/bootstrap/lib/common.sh' 2>/dev/null
        deploy_home_skills '$SANDBOX/src' '$SANDBOX/manifest/skills' >/dev/null 2>&1
        find '$SANDBOX/manifest/skills' -name SKILL.md | wc -l | tr -d ' '"
    assert_output --partial "0"
}

@test "deploy_home_skills writes <root>/skills WITH the harness-skills domain" {
    printf 'domains:\n  - skills\nretired: []\n' > "$SANDBOX/apmowned.yml"
    mkdir -p "$SANDBOX/manifest/skills"
    run bash -c "
        print_info() { :; }; print_error() { :; }; print_success() { :; }; print_warning() { :; }
        source '$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh'
        source '$REPO_ROOT/bootstrap/lib/skill_prune.sh'
        export MANIFEST_APM_DOMAINS='$SANDBOX/apmowned.yml'
        source '$REPO_ROOT/bootstrap/lib/common.sh' 2>/dev/null
        deploy_home_skills '$SANDBOX/src' '$SANDBOX/manifest/skills' harness-skills >/dev/null 2>&1
        find '$SANDBOX/manifest/skills' -name SKILL.md | wc -l | tr -d ' '"
    assert_output --partial "1"
}

@test "both deploy.sh call sites pass the harness-skills domain" {
    # Guards the actual wiring: a call site that loses the third argument
    # reproduces the silent no-op above, and no runtime test would catch it
    # because the failure is an empty tree, not an error.
    run grep -c 'deploy_home_skills "\$SCRIPT_DIR/.apm/skills" "\${MANIFEST_SKILLS_DIR:-\$TARGET_DIR/skills}" harness-skills' \
        "$REPO_ROOT/bootstrap/lib/deploy.sh"
    assert_success
    [ "$output" -eq 2 ]
}
