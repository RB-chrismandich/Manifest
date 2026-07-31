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

# --- T1.11 (spec 674): the two additive, self-disabling owners --------------
#
# Every case below is checked in BOTH directions. A row that is always absent
# and a row that is always red are indistinguishable from a working gate until
# the day someone needs it to fire.

setup_t111() {
    T111="$(mktemp -d "${BATS_TMPDIR:-/tmp}/t111.XXXXXX")"
    mkdir -p "$T111/.claude/skills" "$T111/.claude/plugins" "$T111/.apm"
    # A lockfile claiming the skills domain keeps the pre-existing `skills` row
    # at OWNER=apm and exit 0, so anything red below comes from the new rows.
    printf 'dependencies:\n  - deployed_files:\n      - .claude/skills/demo/SKILL.md\n' \
        > "$T111/.apm/apm.lock.yaml"
    mkdir -p "$T111/.claude/skills/demo"
    printf 'domains:\n  - skills\nretired: []\n' > "$T111/domains.yml"
}

run_report() {
    run env HOME="$T111" MANIFEST_APM_DOMAINS="$T111/domains.yml" \
        APM_LOCKFILE="$T111/.apm/apm.lock.yaml" \
        CLAUDE_PLUGINS_STATE="$T111/.claude/plugins/installed_plugins.json" \
        MANIFEST_SKILLS_DIR="$T111/.manifest/skills" \
        bash "$REPO_ROOT/configs/claude/scripts/apm_ownership_report.sh" "$@"
}

teardown_t111() { [[ -n "${T111:-}" ]] && rm -rf "$T111"; return 0; }

@test "T1.11: neither new row appears on a pre-cutover machine, and exit stays 0" {
    # The regression the task exists to prevent. Adding these owners to DOMAINS
    # unconditionally reports UNOWNED twice and reddens a CORRECT machine.
    setup_t111
    run_report
    refute_output --partial "harness-skills"
    refute_output --partial "plugins"
    [ "$status" -eq 0 ]
    teardown_t111
}

@test "T1.11: a no-match grep does not abort the report" {
    # installed_manifest_bundles greps a file with no manifest-* key. grep exits
    # 1, pipefail propagates, and `set -e` killed the whole script -- no header,
    # no rows, exit 1 -- on every machine that has not cut over.
    setup_t111
    printf '{"version":1,"plugins":{"remember@claude-plugins-official":{}}}\n' \
        > "$T111/.claude/plugins/installed_plugins.json"
    run_report
    assert_output --partial "DOMAIN"
    [ "$status" -eq 0 ]
    teardown_t111
}

@test "T1.11: the plugins row appears once a manifest bundle is installed" {
    setup_t111
    printf '{"plugins":{"manifest-docs@manifest":{},"remember@claude-plugins-official":{}}}\n' \
        > "$T111/.claude/plugins/installed_plugins.json"
    run_report
    assert_output --partial "plugins"
    [ "$status" -eq 0 ]
    teardown_t111
}

@test "T1.11: a bundle name is matched as a KEY, never as a value" {
    # '"manifest-x@y"' appearing as a value would otherwise conjure a row on a
    # machine with nothing installed.
    setup_t111
    printf '{"plugins":{},"note":"manifest-docs@manifest"}\n' \
        > "$T111/.claude/plugins/installed_plugins.json"
    run_report
    refute_output --partial "plugins  "
    [ "$status" -eq 0 ]
    teardown_t111
}

@test "T1.11: a skill in BOTH a bundle and ~/.claude/skills is DOUBLE-CLAIMED" {
    setup_t111
    printf '{"plugins":{"manifest-docs@manifest":{}}}\n' \
        > "$T111/.claude/plugins/installed_plugins.json"
    mkdir -p "$T111/.claude/plugins/cache/manifest/manifest-docs/skills/demo"
    run_report
    assert_output --partial "DOUBLE-CLAIMED"
    assert_output --partial "demo"
    [ "$status" -eq 1 ]
    teardown_t111
}

@test "T1.11: harness-skills reports manifest when every sibling resolves" {
    setup_t111
    mkdir -p "$T111/.manifest/skills/demo"
    for h in .cursor .gemini .codex .antigravity; do
        mkdir -p "$T111/$h"
        ln -s "$T111/.manifest/skills" "$T111/$h/skills"
    done
    run_report
    assert_output --partial "harness-skills"
    assert_output --partial "manifest"
    [ "$status" -eq 0 ]
    teardown_t111
}

@test "T1.11: a diverted sibling is PARTIAL and is named" {
    setup_t111
    mkdir -p "$T111/.manifest/skills/demo" "$T111/elsewhere"
    for h in .cursor .gemini .codex; do
        mkdir -p "$T111/$h"
        ln -s "$T111/.manifest/skills" "$T111/$h/skills"
    done
    mkdir -p "$T111/.antigravity"
    ln -s "$T111/elsewhere" "$T111/.antigravity/skills"
    run_report
    assert_output --partial "PARTIAL"
    assert_output --partial ".antigravity"
    [ "$status" -eq 1 ]
    teardown_t111
}

@test "T1.11: Devin is deliberately NOT a checked sibling" {
    # ~/.config/devin/skills is not created until Phase 4. Checking it here
    # would turn every correct Phase-2 machine red.
    #
    # The devin path must EXIST for this to prove anything: the loop skips a
    # sibling whose skills entry is absent, so an empty ~/.config/devin leaves
    # the assertion green whether devin is checked or not. A real directory --
    # devin serving its own skills, resolving nowhere near the harness tree --
    # is the state where the exclusion is load-bearing.
    setup_t111
    mkdir -p "$T111/.manifest/skills/demo" "$T111/.config/devin/skills/its-own"
    for h in .cursor .gemini .codex .antigravity; do
        mkdir -p "$T111/$h"
        ln -s "$T111/.manifest/skills" "$T111/$h/skills"
    done
    run_report
    [ "$status" -eq 0 ]
    teardown_t111
}
