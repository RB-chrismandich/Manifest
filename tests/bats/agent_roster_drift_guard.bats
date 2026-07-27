#!/usr/bin/env bats
# Drift guard (goal-task-E, Part 2): the pre-existing drift guard
# (tests/python/test_agent_roster.py::test_binary_matches_parallel_agent_cli_agents)
# only ever compared ONE field (binary) between agent_roster.yml and
# parallel_agent.yml's cli_agents block. Since then, this goal's work
# (Tasks A-D) added SEVERAL MORE independent hardcoded-default copies of
# roster facts, each used only as an innermost fallback when agent_roster.yml
# itself can't be read:
#   - check_status.sh's tier-3 ROSTER_NAMES/ROSTER_BINARIES/ROSTER_AUTH_CHECKS
#     (both binary AND auth_check -- the two fields it actually consumes)
#   - sync-skills.sh's tier-3 ROSTER_NAMES/ROSTER_HOME_DIRS (home_dir -- the
#     one field it actually consumes)
#   - agents/cli.py's _FALLBACK_ROSTER / _MODEL_TIER_DEFAULTS (names only;
#     guarded in tests/python/agents/test_cli.py::TestCliFallbackDriftGuard)
#   - reconcile_core.py's _DEFAULT_ROOT_TAGS (names only; guarded in
#     tests/python/test_reconcile_policy.py::test_default_root_tags_matches_real_registry_name_set)
#
# check_status.sh and sync-skills.sh embed their fallback as literal bash
# array assignments, which a Python-side test can't evaluate cleanly. These
# two bats tests extract those EXACT lines straight out of the live script
# source (not a copy pasted into the test) and execute them in isolation, then
# diff the result against a live yaml.safe_load() of the REAL
# agent_roster.yml -- so editing either agent_roster.yml or a script's
# fallback without updating the other fails here, not silently.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CHECK_STATUS="$REPO_ROOT/configs/claude/scripts/check_status.sh"
SYNC_SKILLS="$REPO_ROOT/configs/claude/scripts/sync-skills.sh"
ROSTER="$REPO_ROOT/configs/claude/config/agent_roster.yml"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TEST_TMP=$(mktemp -d "$BATS_TMPDIR/agent_roster_drift_guard.XXXXXX")
}

teardown() {
    [[ -n "$TEST_TMP" && -d "$TEST_TMP" ]] && rm -rf "$TEST_TMP"
}

@test "check_status.sh tier-3 fallback binary+auth_check match agent_roster.yml for all 5 known agents" {
    # Extract ONLY the 3 array-assignment lines inside check_status.sh's
    # `if [[ \${#ROSTER_NAMES[@]} -eq 0 ]]; then ... fi` tier-3 block and eval
    # them in an isolated bash subshell -- this is the script's real, current
    # fallback literal, not a value hand-copied into this test.
    fallback_src="$(sed -n '/^    ROSTER_NAMES=(claude gemini cursor codex antigravity)$/,/^    ROSTER_AUTH_CHECKS=/p' "$CHECK_STATUS")"
    [ -n "$fallback_src" ] # sanity: the anchor pattern must still match the live script

    fallback_tsv="$(bash -c "
        $fallback_src
        for i in \"\${!ROSTER_NAMES[@]}\"; do
            printf '%s\t%s\t%s\n' \"\${ROSTER_NAMES[\$i]}\" \"\${ROSTER_BINARIES[\$i]}\" \"\${ROSTER_AUTH_CHECKS[\$i]}\"
        done
    " | sort)"

    roster_tsv="$(python3 - "$ROSTER" << 'PY' | sort
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    agents = yaml.safe_load(fh)["agents"]
for name in ("claude", "gemini", "cursor", "codex", "antigravity"):
    entry = agents[name]
    print(f"{name}\t{entry['binary']}\t{entry['auth_check']}")
PY
    )"

    assert_equal "$fallback_tsv" "$roster_tsv"
}

@test "sync-skills.sh tier-3 fallback home_dir matches agent_roster.yml for all 5 known agents" {
    fallback_src="$(sed -n '/^    ROSTER_NAMES=(claude gemini cursor codex antigravity)$/,/^    ROSTER_HOME_DIRS=/p' "$SYNC_SKILLS")"
    [ -n "$fallback_src" ] # sanity: the anchor pattern must still match the live script

    # sync-skills.sh's fallback interpolates "$HOME/.claude" etc -- fix HOME
    # to a sentinel so the comparison is against the ~-form agent_roster.yml
    # actually stores, not this test runner's real $HOME. Written to a temp
    # script (not inlined into `bash -c "..."`) to sidestep nested-quoting
    # escaping of the '/SENTINEL_HOME' -> '~' substitution below.
    driver="$TEST_TMP/driver.sh"
    {
        printf '%s\n' "$fallback_src"
        cat << 'DRIVER'
for i in "${!ROSTER_NAMES[@]}"; do
    home="${ROSTER_HOME_DIRS[$i]}"
    home="${home/#\/SENTINEL_HOME/~}"
    printf '%s\t%s\n' "${ROSTER_NAMES[$i]}" "$home"
done
DRIVER
    } > "$driver"
    fallback_tsv="$(HOME=/SENTINEL_HOME bash "$driver" | sort)"

    roster_tsv="$(python3 - "$ROSTER" << 'PY' | sort
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    agents = yaml.safe_load(fh)["agents"]
for name in ("claude", "gemini", "cursor", "codex", "antigravity"):
    print(f"{name}\t{agents[name]['home_dir']}")
PY
    )"

    assert_equal "$fallback_tsv" "$roster_tsv"
}
