#!/usr/bin/env bats
# T053/FR-039/FR-019: the un-gate + reclamation escape hatch.
#
# Phase 2 deliberately leaves a domain with no writer. That is only safe if a
# domain can be handed BACK mid-migration, and if handing it back also removes
# what APM already wrote — otherwise the domain ends up owned by neither
# pipeline, which is the untracked-hybrid state the whole feature exists to
# eliminate.
#
# The end-state assertion that matters is the last test: after un-gating, the
# domain has exactly ONE owner again, proven with the same behavioural probe
# apm_ownership_boundary.bats uses rather than by inspecting config.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/apm_ungate_domain.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_ungate.XXXXXX")"

    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.claude/skills"

    export MANIFEST_ROOT="$SANDBOX/repo"
    SRC="$MANIFEST_ROOT/.apm/skills"
    for s in alpha beta; do
        mkdir -p "$SRC/$s"
        printf -- '---\nname: %s\ndescription: d\n---\nbody\n' "$s" > "$SRC/$s/SKILL.md"
    done

    # Gated state: APM owns skills.
    export MANIFEST_APM_DOMAINS="$SANDBOX/domains.yml"
    printf 'domains:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"

    # An APM deploy that already happened: two files it owns, plus one file a
    # DIFFERENT tool installed into the same directory. Reclamation must remove
    # the former and leave the latter alone.
    mkdir -p "$HOME/.claude/skills/alpha" "$HOME/.claude/skills/foreign"
    echo "apm" > "$HOME/.claude/skills/alpha/SKILL.md"
    echo "someone else" > "$HOME/.claude/skills/foreign/SKILL.md"

    export APM_LOCKFILE="$SANDBOX/apm.lock.yaml"
    cat > "$APM_LOCKFILE" << 'YML'
lockfile_version: '1'
dependencies:
- repo_url: _local/manifest-skills
  deployed_files:
  - .claude/skills/alpha
  - .claude/skills/alpha/SKILL.md
YML

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    print_success() { :; }
    print_warning() { :; }
    print_error() { :; }
    print_info() { :; }
    print_step() { :; }
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "--help exits 0 and prints usage" {
    run "$SCRIPT" --help
    assert_success
    assert_output --partial "Usage: apm_ungate_domain.sh"
}

@test "dry run is the default and changes nothing" {
    run "$SCRIPT" skills
    assert_success
    assert_output --partial "DRY RUN"

    run cat "$MANIFEST_APM_DOMAINS"
    assert_output --partial "skills"
    [ -f "$HOME/.claude/skills/alpha/SKILL.md" ]
}

@test "dry run lists the APM-deployed paths it would reclaim" {
    run "$SCRIPT" skills
    assert_success
    assert_output --partial ".claude/skills/alpha"
}

@test "refuses a domain that is not gated" {
    run "$SCRIPT" config
    assert_failure
    assert_output --partial "not listed"
}

@test "--apply removes the domain from the registry" {
    run "$SCRIPT" skills --apply
    assert_success

    run cat "$MANIFEST_APM_DOMAINS"
    refute_output --partial "- skills"
}

@test "--apply reclaims what APM deployed" {
    run "$SCRIPT" skills --apply
    assert_success
    [ ! -e "$HOME/.claude/skills/alpha" ]
}

@test "--apply leaves files APM did not deploy alone" {
    # The reason reclamation reads the lockfile instead of globbing the
    # directory: ~/.claude/skills legitimately holds other tools' skills.
    run "$SCRIPT" skills --apply
    assert_success
    [ -f "$HOME/.claude/skills/foreign/SKILL.md" ]
}

@test "an empty deployed-file inventory is reported, not silently passed over" {
    # A lockfile with no inventory means reclamation cannot be VERIFIED. Saying
    # "nothing to reclaim" would present an unverifiable state as a clean one.
    printf "lockfile_version: '1'\ndependencies: []\n" > "$APM_LOCKFILE"

    run "$SCRIPT" skills
    assert_success
    assert_output --partial "NONE FOUND"
    assert_output --partial "owned by neither pipeline"
}

@test "a lockfile path escaping HOME is refused, not followed" {
    # Same shape apm really writes — `deployed_files:` on its own indented line.
    cat > "$APM_LOCKFILE" << 'YML'
dependencies:
- repo_url: _local/manifest-skills
  deployed_files:
  - ../../etc/passwd
  - /tmp/absolute
YML
    run "$SCRIPT" skills --apply
    assert_success
    assert_output --partial "refusing to reclaim suspicious path"
}

@test "after un-gating, the domain has exactly one live writer again" {
    # The end state T053 is actually for. Probed behaviourally, the same way
    # apm_ownership_boundary.bats does it — config inspection would not prove
    # the legacy writer actually resumed.
    run "$SCRIPT" skills --apply
    assert_success

    rm -rf "$HOME/.claude/skills"
    run deploy_home_skills "$SRC" "$HOME/.claude/skills"
    assert_success
    [ -f "$HOME/.claude/skills/alpha/SKILL.md" ]

    run env MANIFEST_ROOT="$MANIFEST_ROOT" MANIFEST_APM_DOMAINS="$MANIFEST_APM_DOMAINS" \
        MANIFEST_AGENT_ROSTER="$SANDBOX/absent.yml" \
        bash "$REPO_ROOT/configs/claude/scripts/sync-skills.sh"
    refute_output --partial "APM owns this domain"
}

@test "after un-gating, the ownership REPORT also reads single-owner" {
    # Regression. The suite previously asserted only the writer side — that
    # deploy_home_skills resumed — and never re-read the report. It didn't:
    # reclaiming the files left the lockfile still listing them, so
    # apm_ownership_report.sh stayed on DOUBLE-CLAIMED forever after a
    # successful rollback. Caught by running the tool, not by these tests.
    run "$SCRIPT" skills --apply
    assert_success

    run env HOME="$HOME" MANIFEST_APM_DOMAINS="$MANIFEST_APM_DOMAINS" \
        APM_LOCKFILE="$APM_LOCKFILE" \
        "$REPO_ROOT/configs/claude/scripts/apm_ownership_report.sh"
    assert_success
    assert_output --partial "legacy"
    refute_output --partial "DOUBLE-CLAIMED"
}

@test "un-gating drops only the target domain's claim from the lockfile" {
    # A blunt "delete the lockfile" would also discard other domains' records.
    cat > "$APM_LOCKFILE" << 'YML'
dependencies:
- repo_url: _local/manifest-skills
  deployed_files:
  - .claude/skills/alpha/SKILL.md
- repo_url: _local/manifest-agents
  deployed_files:
  - .claude/agents/keep-me.md
YML
    run "$SCRIPT" skills --apply
    assert_success

    run cat "$APM_LOCKFILE"
    assert_output --partial "keep-me.md"
    refute_output --partial ".claude/skills/alpha"
}
