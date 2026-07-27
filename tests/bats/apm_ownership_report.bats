#!/usr/bin/env bats
# T010/FR-015/SC-006 — the ownership diagnostic, plus T011/FR-019's per-domain
# deploy selector.
#
# Both exist to make the coexistence window survivable rather than to describe
# it afterwards: the diagnostic names a double-claimed or unowned domain while
# the migration is in flight, and the selector is what makes "redeploy only the
# unmigrated domains" an action anyone can actually take.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
REPORT="$REPO_ROOT/configs/claude/scripts/apm_ownership_report.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_own_report.XXXXXX")"
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude/skills"

    export MANIFEST_APM_DOMAINS="$SANDBOX/domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"
    export APM_LOCKFILE="$SANDBOX/apm.lock.yaml"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/configs/claude/scripts/apm_domains_lib.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    print_success() { :; }
    print_warning() { :; }
    print_error() { :; }
    print_info() { :; }
    print_step() { :; }

    SRC="$SANDBOX/src"
    mkdir -p "$SRC/alpha"
    printf -- '---\nname: alpha\ndescription: d\n---\nbody\n' > "$SRC/alpha/SKILL.md"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

lockfile_claims_skills() {
    cat > "$APM_LOCKFILE" << 'YML'
dependencies:
- repo_url: _local/manifest-skills
  deployed_files:
  - .claude/skills/alpha/SKILL.md
YML
}

# --- T010: the diagnostic ----------------------------------------------------

@test "--help exits 0 and prints usage" {
    run "$REPORT" --help
    assert_success
    assert_output --partial "Usage: apm_ownership_report.sh"
}

@test "legacy-owned is the normal state today and exits 0" {
    run "$REPORT"
    assert_success
    assert_output --partial "legacy"
}

@test "a domain written by BOTH pipelines is flagged and exits non-zero" {
    # The drift condition the whole feature exists to remove.
    lockfile_claims_skills   # apm deployed it...
    # ...and the registry does not gate the legacy writer, so both write it.
    run "$REPORT"
    assert_failure
    assert_output --partial "DOUBLE-CLAIMED"
    assert_output --partial "BOTH pipelines"
}

@test "a domain written by NEITHER pipeline is flagged, and names the escape hatch" {
    # Gated but not yet deployed by apm — the Phase 2 window. Safe there, a bug
    # anywhere else, and silent either way without this report.
    printf 'domains:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"
    run "$REPORT"
    assert_failure
    assert_output --partial "UNOWNED"
    assert_output --partial "apm_ungate_domain.sh skills --apply"
}

@test "apm-owned and apm-deployed is a clean single-owner state" {
    printf 'domains:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"
    lockfile_claims_skills
    run "$REPORT"
    assert_success
    assert_output --partial "apm"
    refute_output --partial "DOUBLE-CLAIMED"
}

@test "--json is parseable and carries the ok flag" {
    run "$REPORT" --json
    assert_success
    run bash -c "'$REPORT' --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[\"ok\"], d[\"domains\"][0][\"domain\"])'"
    assert_output "True skills"
}

@test "the report never writes anything" {
    before="$(find "$HOME" | LC_ALL=C sort | shasum -a 256)"
    run "$REPORT"
    after="$(find "$HOME" | LC_ALL=C sort | shasum -a 256)"
    [ "$before" = "$after" ]
}

# --- T011: the per-domain deploy selector ------------------------------------

@test "an unset selector deploys everything — the selector is inert by default" {
    # If an unset list meant "nothing", every existing bootstrap run would
    # silently become a no-op deploy.
    unset MANIFEST_DEPLOY_DOMAINS
    run deploy_domain_selected skills
    assert_success
}

@test "an empty selector also means all" {
    MANIFEST_DEPLOY_DOMAINS="" run deploy_domain_selected skills
    assert_success
}

@test "a selector naming the domain includes it" {
    MANIFEST_DEPLOY_DOMAINS="skills,config" run deploy_domain_selected skills
    assert_success
}

@test "a selector omitting the domain excludes it" {
    MANIFEST_DEPLOY_DOMAINS="config" run deploy_domain_selected skills
    assert_failure
}

@test "whitespace around list entries is tolerated" {
    MANIFEST_DEPLOY_DOMAINS="config, skills" run deploy_domain_selected skills
    assert_success
}

@test "deploy_home_skills honours the selector without touching the domain" {
    MANIFEST_DEPLOY_DOMAINS="config" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null
    [ ! -e "$HOME/.claude/skills/alpha" ]
}

@test "deploy_home_skills still deploys when the selector names it" {
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null
    [ -f "$HOME/.claude/skills/alpha/SKILL.md" ]
}

@test "an unknown flag is rejected, not silently ignored" {
    # Regression: --json was matched positionally and anything else fell through
    # to the human-readable report with exit 0, so a typo'd --jsonn handed
    # human text to a caller that asked for JSON.
    run "$REPORT" --bogus
    assert_failure
    assert_output --partial "unknown argument"
}

@test "the path column renders a real tilde, not an escaped one" {
    # Regression: the substitution emitted a literal backslash — "\~/.claude".
    run "$REPORT"
    assert_success
    assert_output --partial "~/.claude/skills"
    refute_output --partial '\~'
}
