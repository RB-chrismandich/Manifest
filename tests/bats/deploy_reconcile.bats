#!/usr/bin/env bats
# Tests for configs/claude/scripts/deploy_reconcile.sh (feature 368).
# Read-only classification is unit-tested in tests/python/test_reconcile_policy.py;
# these cover the CLI, the destructive --remove path, and fail-open behavior.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/deploy_reconcile.sh"
CONFIG="$REPO_ROOT/configs/claude/config/reconcile.yml"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/reconcile.XXXXXX")
    BASE="$SANDBOX/home"
    PROJ="$SANDBOX/repo"
    export MANIFEST_STATE_ROOT="$SANDBOX/state"
    export MANIFEST_VENV_PY="${MANIFEST_VENV_PY:-python3}"
    mkdir -p "$BASE/.claude/skills/live" "$BASE/.claude/skills/dead" "$BASE/.claude/config" "$BASE/.cursor"
    echo "x" > "$BASE/.claude/skills/live/SKILL.md"
    echo "x" > "$BASE/.claude/skills/dead/SKILL.md"
    echo "manifest" > "$BASE/.claude/skills/.deployed-skills"
    echo "y: 1" > "$BASE/.claude/config/command_config.yml"
    echo "stale" > "$BASE/.claude/config/old_layout.yml"
    echo "{}" > "$BASE/.claude/config/config.json"
    ln -s "$BASE/.claude/skills" "$BASE/.cursor/skills"   # shared parent-dir symlink
    mkdir -p "$PROJ/.apm/skills/live" "$PROJ/configs/claude/config"
    echo "y: 1" > "$PROJ/configs/claude/config/command_config.yml"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

run_review() { run "$SCRIPT" --home "$BASE" --project "$PROJ" --config "$CONFIG" "$@"; }

@test "--help exits 0, is <=15 lines, needs no project/home" {
    run "$SCRIPT" --help
    assert_success
    [ "${#lines[@]}" -le 15 ]
    assert_output --partial "Usage: deploy_reconcile.sh"
}

@test "preview is non-mutating (SC-002)" {
    before=$(find "$BASE" | sort | md5 2>/dev/null || find "$BASE" | sort | md5sum)
    run_review
    assert_success
    after=$(find "$BASE" | sort | md5 2>/dev/null || find "$BASE" | sort | md5sum)
    assert_equal "$before" "$after"
}

@test "classifies orphans REMOVE and prints summary wording (FR-002/FR-004)" {
    run_review
    assert_success
    assert_output --partial "Summary: 4 orphans  |  2 KEEP  |  2 REMOVE"
    assert_output --partial "skills/dead"
    assert_output --partial "config/old_layout.yml"
}

@test "reconciled (project-present) units are not listed (FR-001)" {
    run_review
    refute_output --partial "skills/live "
    refute_output --partial "command_config.yml"
}

@test "protection keeps runtime files, never REMOVE (FR-007/FR-014/SC-004)" {
    run_review --json
    assert_success
    # config.json and .deployed-skills are KEEP/protected
    echo "$output" | python3 -c 'import json,sys
d=json.load(sys.stdin)
prot=[i for i in d["items"] if i["reason_code"]=="protected"]
assert all(i["verdict"]=="KEEP" for i in prot), "protected must be KEEP"
names={i["display_path"].split("/.claude/",1)[1] for i in prot}
assert "config/config.json" in names and "skills/.deployed-skills" in names, names'
}

@test "dedup: shared symlinked orphan reported once (FR-017)" {
    run_review --json
    n=$(echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(1 for i in d["items"] if i["canonical_path"].endswith("/.claude/skills/dead")))')
    assert_equal "$n" "1"
}

@test "clean state reports zero orphans (FR-012)" {
    rm -rf "$BASE/.claude/skills/dead" "$BASE/.claude/config/old_layout.yml" \
           "$BASE/.claude/config/config.json" "$BASE/.claude/skills/.deployed-skills"
    run_review
    assert_success
    assert_output --partial "No orphans found."
}

@test "missing ~/.claude is not an error" {
    rm -rf "$BASE/.claude"
    run_review
    assert_success
    assert_output --partial "0 orphans"
}

@test "unresolvable project exits 2" {
    run "$SCRIPT" --home "$BASE" --project "$SANDBOX/nope" --config "$CONFIG"
    assert_equal "$status" 2
}

@test "--backup-dir inside a managed root is refused (exit 2)" {
    run "$SCRIPT" --home "$BASE" --project "$PROJ" --config "$CONFIG" \
        --remove --yes --backup-dir "$BASE/.claude/trash"
    assert_equal "$status" 2
    assert_output --partial "refusing"
}

@test "--remove --yes moves only REMOVE, keeps KEEP + live, dangle-safe (FR-010/SC-005)" {
    run_review --remove --yes
    assert_success
    [ ! -e "$BASE/.claude/skills/dead" ]
    [ ! -e "$BASE/.claude/config/old_layout.yml" ]
    [ -d "$BASE/.claude/skills/live" ]
    [ -f "$BASE/.claude/config/config.json" ]            # protected KEEP untouched
    [ -e "$BASE/.cursor/skills/live/SKILL.md" ]          # secondary symlink still resolves
}

@test "removal is recoverable via restore.sh, backup excluded from re-scan (SC-008/edge)" {
    run_review --remove --yes
    assert_success
    ts_dir=$(ls -d "$SANDBOX"/state/reconcile-trash/*/)
    [ -f "${ts_dir}removed.tsv" ]
    # second scan is clean (backup is outside managed scope)
    run_review --json
    rem=$(echo "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary"]["remove"])')
    assert_equal "$rem" "0"
    bash "${ts_dir}restore.sh"
    [ -d "$BASE/.claude/skills/dead" ]
}

@test "--remove without --yes (non-interactive) removes nothing (FR-011)" {
    run_review --remove
    assert_success
    assert_output --partial "requires confirmation"
    [ -d "$BASE/.claude/skills/dead" ]                   # still present
}


# --- T1.8 (spec 674): the user's own plugin-init scaffold is not an orphan ---
#
# `claude plugin init <name>` scaffolds into ~/.claude/skills/<name>/ and
# auto-loads it as <name>@skills-dir. Once Manifest stops sourcing that tree,
# every such directory looks exactly like an orphan to this engine, and the
# documented-as-recoverable `--remove` would sweep up the user's own work.
#
# The fix is deliberately NOT a blanket `skills/*`: that protects the whole tree
# and silently disables orphan detection inside it -- the same class of failure
# as the incident that ate deploy_stamp/.migrated, only inverted. Protection is
# keyed on skill_policies.yml, so both directions are asserted below.

setup_registry_project() {
    # A project that IS a Manifest project: it carries the registry, and the
    # registry names `dead` (Manifest's own, retired from the project) but not
    # `mine` (the user's scaffold).
    mkdir -p "$BASE/.claude/skills/mine"
    echo "x" > "$BASE/.claude/skills/mine/SKILL.md"
    printf 'expected_total: 1\nbundles:\n  manifest-demo:\n    - dead\n' \
        > "$PROJ/configs/claude/config/skill_policies.yml"
}

verdict_of() {
    python3 -c '
import json, sys
d = json.load(sys.stdin)
hits = [i for i in d["items"] if i["display_path"].endswith(sys.argv[1])]
print(hits[0]["verdict"] + " " + hits[0]["reason_code"] if hits else "ABSENT")
' "$1"
}

@test "T1.8: a hand-created skill absent from the registry is KEEP, not an orphan" {
    setup_registry_project
    run_review --json
    assert_success
    result="$(printf '%s' "$output" | verdict_of "skills/mine")"
    [ "$result" = "KEEP user_owned_skill" ] || { echo "got: $result"; false; }
}

@test "T1.8: a registry-named skill with no project source is still REMOVE" {
    # The direction that proves the protection is SELECTIVE. If this goes KEEP,
    # orphan detection inside skills/ is off and nothing else reports it.
    setup_registry_project
    run_review --json
    assert_success
    result="$(printf '%s' "$output" | verdict_of "skills/dead")"
    [ "${result%% *}" = "REMOVE" ] || { echo "got: $result"; false; }
}

@test "T1.8: a project with no registry protects nothing — the pre-existing behaviour" {
    # No skill_policies.yml means "not a Manifest project", which must stay
    # distinct from "a Manifest project shipping no skills". Collapsing the two
    # protects every skills/ entry on every non-Manifest project at once.
    mkdir -p "$BASE/.claude/skills/mine"
    echo "x" > "$BASE/.claude/skills/mine/SKILL.md"
    run_review --json
    assert_success
    result="$(printf '%s' "$output" | verdict_of "skills/mine")"
    [ "${result%% *}" = "REMOVE" ] || { echo "got: $result"; false; }
}
