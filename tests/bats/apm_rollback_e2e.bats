#!/usr/bin/env bats
# T034/FR-019 — prove the rollback on a PARTIALLY MIGRATED machine, end to end.
#
# The individual pieces are already tested: T011's selective deploy, T053's
# un-gate and reclamation, T010's ownership report. This asserts the property
# none of them can assert alone — that following the documented procedure on a
# half-migrated machine lands you somewhere a never-migrated machine would also
# be, with nothing stripped and nothing orphaned.
#
# The acceptance criterion is a DIFF against a never-migrated control, not a
# spot-check. Spot-checking "are my skills back?" would pass while an APM-written
# file nobody owns sits in the tree — which is the untracked-hybrid state this
# whole feature exists to eliminate, so a rollback that leaves one has failed
# even though everything looks fine.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
UNGATE="$REPO_ROOT/configs/claude/scripts/apm_ungate_domain.sh"
REPORT="$REPO_ROOT/configs/claude/scripts/apm_ownership_report.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_rollback.XXXXXX")"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    print_success() { :; }
    print_warning() { :; }
    print_error() { :; }
    print_info() { :; }
    print_step() { :; }

    SRC="$SANDBOX/src"
    for s in alpha beta gamma; do
        mkdir -p "$SRC/$s"
        printf -- '---\nname: %s\ndescription: d\n---\nbody\n' "$s" > "$SRC/$s/SKILL.md"
    done

    export MANIFEST_APM_DOMAINS="$SANDBOX/domains.yml"
    export APM_LOCKFILE="$SANDBOX/apm.lock.yaml"

    # --- the CONTROL: a machine that never migrated ---------------------------
    CONTROL="$SANDBOX/control"
    mkdir -p "$CONTROL/.claude"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"
    HOME="$CONTROL" deploy_home_skills "$SRC" "$CONTROL/.claude/skills" > /dev/null

    # --- the SUBJECT: a machine mid-migration --------------------------------
    # Gated (legacy stood down) AND apm deployed, including one file the legacy
    # pipeline would never write — the orphan a naive rollback leaves behind.
    export HOME="$SANDBOX/subject"
    mkdir -p "$HOME/.claude/skills"
    printf 'domains:\n  - skills\n' > "$MANIFEST_APM_DOMAINS"
    for s in alpha beta gamma; do
        mkdir -p "$HOME/.claude/skills/$s"
        cp "$SRC/$s/SKILL.md" "$HOME/.claude/skills/$s/SKILL.md"
    done
    mkdir -p "$HOME/.claude/skills/apm-only-primitive"
    echo "written by apm, unknown to the legacy pipeline" \
        > "$HOME/.claude/skills/apm-only-primitive/SKILL.md"

    cat > "$APM_LOCKFILE" << 'YML'
lockfile_version: '1'
dependencies:
- repo_url: _local/manifest-skills
  deployed_files:
  - .claude/skills/alpha
  - .claude/skills/alpha/SKILL.md
  - .claude/skills/beta
  - .claude/skills/beta/SKILL.md
  - .claude/skills/gamma
  - .claude/skills/gamma/SKILL.md
  - .claude/skills/apm-only-primitive
  - .claude/skills/apm-only-primitive/SKILL.md
YML
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

tree_of() { (cd "$1" && find . -type f ! -name '.deployed-skills' | LC_ALL=C sort); }

@test "precondition: the subject really is partially migrated" {
    # Without this the whole test could pass against a machine that was never
    # in the state the rollback is meant to recover from.
    run "$REPORT"
    assert_success
    assert_output --partial "apm"
    [ -f "$HOME/.claude/skills/apm-only-primitive/SKILL.md" ]
}

@test "the documented rollback restores a working configuration" {
    run "$UNGATE" skills --apply
    assert_success

    # Step 2 of the procedure: redeploy the domain via the legacy pipeline.
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null

    [ -f "$HOME/.claude/skills/alpha/SKILL.md" ]
    [ -f "$HOME/.claude/skills/beta/SKILL.md" ]
    [ -f "$HOME/.claude/skills/gamma/SKILL.md" ]
}

@test "no APM-written orphan survives the rollback" {
    # The failure a spot-check misses: apm-only-primitive is not produced by the
    # legacy pipeline, so redeploying alone would leave it owned by nobody.
    "$UNGATE" skills --apply > /dev/null
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null

    [ ! -e "$HOME/.claude/skills/apm-only-primitive" ]
}

@test "no legacy-owned file was stripped" {
    "$UNGATE" skills --apply > /dev/null
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null

    n="$(find "$HOME/.claude/skills" -name SKILL.md | wc -l | tr -d ' ')"
    [ "$n" = "3" ]
}

@test "the rolled-back tree DIFFS CLEAN against a never-migrated control" {
    # T034's actual acceptance criterion. Everything above could pass while the
    # trees still differ somewhere nobody thought to spot-check.
    "$UNGATE" skills --apply > /dev/null
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null

    run diff <(tree_of "$CONTROL/.claude/skills") <(tree_of "$HOME/.claude/skills")
    assert_success
}

@test "the diff is not vacuous — it detects a planted difference" {
    # A diff of two empty trees also passes. Prove the comparison discriminates
    # before trusting the clean result above.
    "$UNGATE" skills --apply > /dev/null
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null
    mkdir -p "$HOME/.claude/skills/planted"
    echo x > "$HOME/.claude/skills/planted/SKILL.md"

    run diff <(tree_of "$CONTROL/.claude/skills") <(tree_of "$HOME/.claude/skills")
    assert_failure
}

@test "after rollback the domain has exactly one owner" {
    "$UNGATE" skills --apply > /dev/null
    MANIFEST_DEPLOY_DOMAINS="skills" deploy_home_skills "$SRC" "$HOME/.claude/skills" > /dev/null

    run "$REPORT"
    assert_success
    assert_output --partial "legacy"
    refute_output --partial "DOUBLE-CLAIMED"
}
