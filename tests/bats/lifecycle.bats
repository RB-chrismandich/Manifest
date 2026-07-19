#!/usr/bin/env bats
# Tests for configs/claude/scripts/lifecycle.sh — the codified state-gated lifecycle.
# Contract: specs/365-lifecycle-codification/contracts/lifecycle-cli.md

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/lifecycle.sh"

setup() {
    LIFECYCLE_STATE_DIR="$BATS_TEST_TMPDIR/state"
    export LIFECYCLE_STATE_DIR
}

action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }
field()  { python3 -c "import json,sys;print(json.load(sys.stdin).get('$1') or '')"; }

ALL_BUT_LAST='["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement"]'

# --- CLI surface ---
@test "--help exits 0 and mentions decide (before any state lookup)" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]; [[ "$output" == *"decide"* ]]
}
@test "unknown subcommand exits non-zero" {
    run "$SCRIPT" bogus
    [ "$status" -ne 0 ]
}

# --- decide: pure core, always exit 0, fail-closed ---
@test "decide always exits 0 even on garbage" {
    run "$SCRIPT" decide 'not json at all'
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "decide fail-closed on unknown current_phase" {
    run "$SCRIPT" decide '{"current_phase":"bogus"}'
    [ "$(echo "$output" | action)" = "refuse" ]
}

# --- skip detection ---
@test "agent skip-ahead -> refuse, names first missing prerequisite" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$(echo "$output" | action)" = "refuse" ]
    [ "$(echo "$output" | field missing_prereq)" = "spec_review_product" ]
}
@test "human skip-ahead -> warn (advisory), not refuse" {
    run "$SCRIPT" decide '{"actor_mode":"human","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$(echo "$output" | action)" = "warn" ]
}

# --- gate evaluation per gate_type ---
@test "verdict APPROVED -> allow" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"spec_review_product","completed_phases":["specify","clarify"],"phase_gate":{"gate_type":"verdict","verdict":"APPROVED"}}'
    [ "$(echo "$output" | action)" = "allow" ]
}
@test "verdict BLOCKED -> refuse (agent)" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"spec_review_product","completed_phases":["specify","clarify"],"phase_gate":{"gate_type":"verdict","verdict":"BLOCKED"}}'
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "verdict NEEDS_REVIEW -> warn" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"spec_review_product","completed_phases":["specify","clarify"],"phase_gate":{"gate_type":"verdict","verdict":"NEEDS_REVIEW"}}'
    [ "$(echo "$output" | action)" = "warn" ]
}
@test "runner exit 0 -> allow; exit 2 (EMPTY) -> refuse (missing coverage != pass)" {
    run "$SCRIPT" decide "{\"actor_mode\":\"agent\",\"current_phase\":\"verify\",\"requested_phase\":\"verify\",\"completed_phases\":$ALL_BUT_LAST,\"phase_gate\":{\"gate_type\":\"runner\",\"exit_code\":0}}"
    [ "$(echo "$output" | action)" = "allow" ]
    run "$SCRIPT" decide "{\"actor_mode\":\"agent\",\"current_phase\":\"verify\",\"requested_phase\":\"verify\",\"completed_phases\":$ALL_BUT_LAST,\"phase_gate\":{\"gate_type\":\"runner\",\"exit_code\":2}}"
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "coverage MISSING -> refuse (agent)" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"implement","completed_phases":["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech"],"phase_gate":{"gate_type":"coverage","coverage":"MISSING"}}'
    [ "$(echo "$output" | action)" = "refuse" ]
}
@test "artifact present -> allow; missing field -> refuse (fail-closed)" {
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact","present":true}}'
    [ "$(echo "$output" | action)" = "allow" ]
    run "$SCRIPT" decide '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact"}}'
    [ "$(echo "$output" | action)" = "refuse" ]
}

# --- gate (non-zero exit for loop callers) ---
@test "gate exits 1 on refuse, 0 on allow, 3 on warn" {
    run "$SCRIPT" gate '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact","present":true}}'
    [ "$status" -eq 0 ]
    run "$SCRIPT" gate '{"actor_mode":"agent","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$status" -eq 1 ]
    run "$SCRIPT" gate '{"actor_mode":"human","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'
    [ "$status" -eq 3 ]
}

# --- state subcommands ---
@test "init creates a track from a Jira key, status reports phase 1" {
    run "$SCRIPT" init PROJ-123
    [ "$status" -eq 0 ]; [[ "$output" == *"jira"* ]]
    run "$SCRIPT" status jira__PROJ-123 --json
    [ "$status" -eq 0 ]
    [ "$(echo "$output" | field current_phase)" = "specify" ]
}
@test "init on unrecognized entry point -> exit 2, no track" {
    run "$SCRIPT" init "just some text"
    [ "$status" -eq 2 ]
}
@test "init is idempotent (re-init does not clobber)" {
    "$SCRIPT" init PROJ-9 >/dev/null
    run "$SCRIPT" init PROJ-9
    [ "$status" -eq 0 ]; [[ "$output" == *"exists"* ]]
}
@test "advance with passing artifact gate moves specify -> clarify and persists" {
    "$SCRIPT" init PROJ-7 >/dev/null
    run "$SCRIPT" advance jira__PROJ-7 --actor agent --gate '{"gate_type":"artifact","present":true}'
    [ "$status" -eq 0 ]; [[ "$output" == *"specify -> clarify"* ]]
    run "$SCRIPT" status jira__PROJ-7 --json
    [ "$(echo "$output" | field current_phase)" = "clarify" ]
}
@test "advance refused (agent) does not change phase" {
    "$SCRIPT" init PROJ-8 >/dev/null
    run "$SCRIPT" advance jira__PROJ-8 --actor agent --gate '{"gate_type":"artifact","present":false}'
    [ "$status" -eq 1 ]
    run "$SCRIPT" status jira__PROJ-8 --json
    [ "$(echo "$output" | field current_phase)" = "specify" ]
}
@test "advance warn (human) holds without --override, proceeds with it" {
    "$SCRIPT" init PROJ-10 >/dev/null
    run "$SCRIPT" advance jira__PROJ-10 --actor human --gate '{"gate_type":"artifact","present":false}'
    [ "$status" -eq 3 ]
    run "$SCRIPT" advance jira__PROJ-10 --actor human --gate '{"gate_type":"artifact","present":false}' --override "known-stub, tracked separately"
    [ "$status" -eq 0 ]
}
@test "regress requires a reason and rewinds the phase" {
    "$SCRIPT" init PROJ-11 >/dev/null
    "$SCRIPT" advance jira__PROJ-11 --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
    run "$SCRIPT" regress jira__PROJ-11 --to specify
    [ "$status" -eq 2 ]
    run "$SCRIPT" regress jira__PROJ-11 --to specify --reason "defect found downstream"
    [ "$status" -eq 0 ]
    run "$SCRIPT" status jira__PROJ-11 --json
    [ "$(echo "$output" | field current_phase)" = "specify" ]
}
@test "status on missing track -> exit 2" {
    run "$SCRIPT" status jira__NOPE-1
    [ "$status" -eq 2 ]
}

# ============================================================================
# US2 — smoke-backed Verify gate + Implement-exit coverage (T017–T021, T012)
# ============================================================================

# Offline smoke seam. `list` emits the REAL per-app dict shape ({app:[{id,...}]}); `run`
# writes a JUnit (passing testcases named by $SMOKE_JUNIT_IDS) and exits $SMOKE_RUN_EXIT.
mk_smoke_stub() {
    cat > "$BATS_TEST_TMPDIR/smoke.sh" <<'STUB'
#!/usr/bin/env bash
sub="$1"; shift
case "$sub" in
  list) [ -n "${SMOKE_CATALOG:-}" ] && echo "$SMOKE_CATALOG" || echo '{}' ;;
  run)
    junit=""
    while [ $# -gt 0 ]; do case "$1" in --junit) junit="$2"; shift 2 ;; *) shift ;; esac; done
    if [ -n "$junit" ]; then
      { echo '<testsuite>'
        for id in ${SMOKE_JUNIT_IDS:-login}; do echo "<testcase name=\"$id\" classname=\"billing.Lite\"></testcase>"; done
        echo '</testsuite>'; } > "$junit"
    fi
    exit "${SMOKE_RUN_EXIT:-0}" ;;
  *) exit 0 ;;
esac
STUB
    chmod +x "$BATS_TEST_TMPDIR/smoke.sh"
    export LIFECYCLE_SMOKE_CMD="$BATS_TEST_TMPDIR/smoke.sh"
}

# Real-shape single-app catalog helper.
CATALOG_LOGIN='{"billing":[{"id":"login","tier":"Lite","steps":3}]}'

subphase() { python3 -c "import json,sys;print(json.load(sys.stdin)['subtask_states']['$1']['phase'])"; }
sub_verified() { python3 -c "import json,sys;print('$2' in json.load(sys.stdin)['subtask_states']['$1'].get('verified_workflow_ids',[]))"; }

# Advance a fresh track from specify(1) to implement(8) with passing gates.
to_implement() {
    local id="$1" g
    for g in artifact artifact verdict artifact artifact verdict verdict; do
        if [ "$g" = verdict ]; then
            "$SCRIPT" advance "$id" --actor agent --gate '{"gate_type":"verdict","verdict":"APPROVED"}' >/dev/null
        else
            "$SCRIPT" advance "$id" --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
        fi
    done
}

@test "subtask --exempt requires --reason (FR-011)" {
    "$SCRIPT" init PROJ-20 >/dev/null
    run "$SCRIPT" subtask jira__PROJ-20 --id S1 --exempt
    [ "$status" -eq 2 ]
}
@test "subtask --ship records the workflow id on the track" {
    "$SCRIPT" init PROJ-21 >/dev/null
    "$SCRIPT" subtask jira__PROJ-21 --id S1 --ship login >/dev/null
    run "$SCRIPT" status jira__PROJ-21 --json
    [[ "$output" == *'"login"'* ]]
}

@test "implement coverage OK (real dict catalog shape) -> advances to verify" {
    mk_smoke_stub
    export SMOKE_CATALOG="$CATALOG_LOGIN"
    "$SCRIPT" init PROJ-22 >/dev/null
    to_implement jira__PROJ-22
    "$SCRIPT" subtask jira__PROJ-22 --id S1 --ship login >/dev/null
    run "$SCRIPT" advance jira__PROJ-22 --actor agent --unit billing
    [ "$status" -eq 0 ]; [[ "$output" == *"implement -> verify"* ]]
}
@test "regression guard: a flat-list catalog (wrong/old shape) is tolerated too" {
    mk_smoke_stub
    export SMOKE_CATALOG='[{"id":"login","tier":"Lite","steps":3}]'
    "$SCRIPT" init PROJ-22B >/dev/null
    to_implement jira__PROJ-22B
    "$SCRIPT" subtask jira__PROJ-22B --id S1 --ship login >/dev/null
    run "$SCRIPT" advance jira__PROJ-22B --actor agent --unit billing
    [ "$status" -eq 0 ]
}
@test "implement coverage MISSING (shipped workflow absent from catalog) -> refused" {
    mk_smoke_stub
    export SMOKE_CATALOG='{"billing":[]}'
    "$SCRIPT" init PROJ-23 >/dev/null
    to_implement jira__PROJ-23
    "$SCRIPT" subtask jira__PROJ-23 --id S1 --ship login >/dev/null
    run "$SCRIPT" advance jira__PROJ-23 --actor agent --unit billing
    [ "$status" -eq 1 ]
    run "$SCRIPT" status jira__PROJ-23 --json
    [ "$(echo "$output" | field current_phase)" = "implement" ]
}
@test "implement coverage fails CLOSED on malformed smoke output (no crash)" {
    mk_smoke_stub
    export SMOKE_CATALOG='this is not json'
    "$SCRIPT" init PROJ-23C >/dev/null
    to_implement jira__PROJ-23C
    "$SCRIPT" subtask jira__PROJ-23C --id S1 --ship login >/dev/null
    run "$SCRIPT" advance jira__PROJ-23C --actor agent --unit billing
    [ "$status" -eq 1 ]   # refused (fail-closed), not an abort/traceback
    [[ "$output" == *"refused"* ]]
}
@test "implement coverage MISSING (non-exempt subtask has no smoke test) -> refused" {
    mk_smoke_stub
    export SMOKE_CATALOG="$CATALOG_LOGIN"
    "$SCRIPT" init PROJ-24 >/dev/null
    to_implement jira__PROJ-24
    "$SCRIPT" subtask jira__PROJ-24 --id S1 >/dev/null   # subtask with no --ship
    run "$SCRIPT" advance jira__PROJ-24 --actor agent --unit billing
    [ "$status" -eq 1 ]
}
@test "exempt subtask is skipped from the coverage requirement" {
    mk_smoke_stub
    export SMOKE_CATALOG="$CATALOG_LOGIN"
    "$SCRIPT" init PROJ-25 >/dev/null
    to_implement jira__PROJ-25
    "$SCRIPT" subtask jira__PROJ-25 --id S1 --ship login >/dev/null
    "$SCRIPT" subtask jira__PROJ-25 --id S2 --exempt --reason "internal refactor, no UI" >/dev/null
    run "$SCRIPT" advance jira__PROJ-25 --actor agent --unit billing
    [ "$status" -eq 0 ]; [[ "$output" == *"implement -> verify"* ]]
}
@test "human actor: coverage MISSING -> warn (exit 3); --override proceeds" {
    mk_smoke_stub
    export SMOKE_CATALOG='{"billing":[]}'
    "$SCRIPT" init PROJ-30 >/dev/null
    to_implement jira__PROJ-30
    "$SCRIPT" subtask jira__PROJ-30 --id S1 --ship login >/dev/null
    run "$SCRIPT" advance jira__PROJ-30 --actor human --unit billing
    [ "$status" -eq 3 ]
    run "$SCRIPT" advance jira__PROJ-30 --actor human --unit billing --override "stub, tracked separately"
    [ "$status" -eq 0 ]
}

@test "verify gate exit 0 -> done; sub-task phase==done AND verified id recorded (FR-028/T021)" {
    mk_smoke_stub
    export SMOKE_CATALOG="$CATALOG_LOGIN" SMOKE_RUN_EXIT=0 SMOKE_JUNIT_IDS=login
    "$SCRIPT" init PROJ-26 >/dev/null
    to_implement jira__PROJ-26
    "$SCRIPT" subtask jira__PROJ-26 --id S1 --ship login >/dev/null
    "$SCRIPT" advance jira__PROJ-26 --actor agent --unit billing >/dev/null   # implement -> verify
    run "$SCRIPT" advance jira__PROJ-26 --actor agent --unit billing          # verify -> done
    [ "$status" -eq 0 ]
    run "$SCRIPT" status jira__PROJ-26 --json
    [ "$(echo "$output" | field current_phase)" = "done" ]
    [ "$(echo "$output" | subphase S1)" = "done" ]              # discriminating (not a substring match)
    [ "$(echo "$output" | sub_verified S1 login)" = "True" ]    # T021 traceability landed
}
@test "verify gate: run exit 1 -> refused (stays in verify)" {
    mk_smoke_stub
    export SMOKE_CATALOG="$CATALOG_LOGIN" SMOKE_RUN_EXIT=1
    "$SCRIPT" init PROJ-27 >/dev/null
    to_implement jira__PROJ-27
    "$SCRIPT" subtask jira__PROJ-27 --id S1 --ship login >/dev/null
    "$SCRIPT" advance jira__PROJ-27 --actor agent --unit billing >/dev/null   # implement -> verify
    run "$SCRIPT" advance jira__PROJ-27 --actor agent --unit billing
    [ "$status" -eq 1 ]
    run "$SCRIPT" status jira__PROJ-27 --json
    [ "$(echo "$output" | field current_phase)" = "verify" ]
}
@test "verify gate: run exit 2 (EMPTY) -> refused (missing coverage is not a pass)" {
    mk_smoke_stub
    export SMOKE_CATALOG="$CATALOG_LOGIN" SMOKE_RUN_EXIT=2
    "$SCRIPT" init PROJ-28 >/dev/null
    to_implement jira__PROJ-28
    "$SCRIPT" subtask jira__PROJ-28 --id S1 --ship login >/dev/null
    "$SCRIPT" advance jira__PROJ-28 --actor agent --unit billing >/dev/null
    run "$SCRIPT" advance jira__PROJ-28 --actor agent --unit billing
    [ "$status" -eq 1 ]
}
@test "advance implement without --unit errors (needs the smoke app)" {
    "$SCRIPT" init PROJ-29 >/dev/null
    to_implement jira__PROJ-29
    run "$SCRIPT" advance jira__PROJ-29 --actor agent
    [ "$status" -ne 0 ]
}

# ============================================================================
# US3 — four-tier hierarchy provisioning (T022–T027, T012)
# ============================================================================

# Provision seam stub: echoes a fake remote id from the title; title containing FAIL -> error.
mk_provision_stub() {
    cat > "$BATS_TEST_TMPDIR/prov.sh" <<'P'
#!/usr/bin/env bash
# args: provider construct title parent_ext
case "$3" in *FAIL*) exit 1 ;; esac
echo "REMOTE-$(echo "$3" | tr ' ' '-')"
P
    chmod +x "$BATS_TEST_TMPDIR/prov.sh"
    export LIFECYCLE_PROVISION_CMD="$BATS_TEST_TMPDIR/prov.sh"
    export LIFECYCLE_PROVIDERS_CONFIG="$BATS_TEST_DIRNAME/../../configs/claude/config/tracker_providers.yml"
}
nodes() { python3 -c 'import json,sys;print(len(json.load(sys.stdin).get("hierarchy",[])))'; }
tier_count() { python3 -c "import json,sys;H=json.load(sys.stdin).get('hierarchy',[]);print(sum(1 for n in H if n['tier_level']==$1))"; }
tier_state() { python3 -c "import json,sys;H=json.load(sys.stdin).get('hierarchy',[]);print([n['provision_state'] for n in H if n['tier_level']==$1][0])"; }
child_links_entry() { python3 -c '
import json,sys
H=json.load(sys.stdin)["hierarchy"]
entry=next(n for n in H if n.get("source")=="entry")
sub=next(n for n in H if n["tier_level"]==4)
print(sub.get("parent_node_id")==entry["node_id"])'; }

@test "init seeds the entry entity as a present Tier-3 anchor node (FR-016 consume)" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#5" >/dev/null
    run "$SCRIPT" status github__org_repo_5 --json
    [ "$(echo "$output" | nodes)" = "1" ]
    [ "$(echo "$output" | tier_state 3)" = "present" ]
}
@test "provision a Sub-Task (tier 4) under the seeded entry; links top-down to it" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#7" >/dev/null
    run "$SCRIPT" provision github__org_repo_7 --tier 4 --title "OAuth callback" --parent-tier 3
    [ "$status" -eq 0 ]; [[ "$output" == *"provisioned tier 4"* ]]
    run "$SCRIPT" status github__org_repo_7 --json
    [ "$(echo "$output" | nodes)" = "2" ]
    [ "$(echo "$output" | child_links_entry)" = "True" ]   # parent_node_id == entry node_id
}
@test "create-or-adopt is idempotent for the same (tier,key,parent): re-run adopts, no duplicate" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#6" >/dev/null
    "$SCRIPT" provision github__org_repo_6 --tier 4 --key S1 --title "OAuth callback" --parent-tier 3 >/dev/null
    run "$SCRIPT" provision github__org_repo_6 --tier 4 --key S1 --title "OAuth callback" --parent-tier 3
    [ "$status" -eq 0 ]; [[ "$output" == *"adopt"* ]]
    run "$SCRIPT" status github__org_repo_6 --json
    [ "$(echo "$output" | tier_count 4)" = "1" ]
}
@test "distinct same-titled siblings (different --key) do NOT collapse" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#12" >/dev/null
    "$SCRIPT" provision github__org_repo_12 --tier 4 --key S1 --title "Add tests" --parent-tier 3 >/dev/null
    "$SCRIPT" provision github__org_repo_12 --tier 4 --key S2 --title "Add tests" --parent-tier 3 >/dev/null
    run "$SCRIPT" status github__org_repo_12 --json
    [ "$(echo "$output" | tier_count 4)" = "2" ]   # two distinct sub-tasks, not collapsed
}
@test "non-adjacent parent -> error (Sub-Task cannot parent directly under Initiative)" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#13" >/dev/null
    run "$SCRIPT" provision github__org_repo_13 --tier 4 --title "x" --parent-tier 1
    [ "$status" -eq 2 ]; [[ "$output" == *"adjacency"* ]]
}
@test "top-down: provisioning an Epic (tier 2) with no Initiative present -> error" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#8" >/dev/null
    run "$SCRIPT" provision github__org_repo_8 --tier 2 --title "Epic" --parent-tier 1
    [ "$status" -eq 1 ]; [[ "$output" == *"top-down"* ]]
}
@test "missing tier -> configuration error naming the tier (FR-014)" {
    mk_provision_stub
    cat > "$BATS_TEST_TMPDIR/prov.yml" <<'Y'
providers:
  github:
    tier_map:
      2: milestone
      3: issue
      4: sub_issue
    missing_tier_behavior: error
Y
    export LIFECYCLE_PROVIDERS_CONFIG="$BATS_TEST_TMPDIR/prov.yml"
    "$SCRIPT" init "org/repo#9" >/dev/null
    run "$SCRIPT" provision github__org_repo_9 --tier 1 --title "Initiative X"
    [ "$status" -eq 2 ]; [[ "$output" == *"tier 1 has no native construct"* ]]
}
@test "missing_tier_behavior fails CLOSED on an unknown value (no silent label collapse, FR-014)" {
    mk_provision_stub
    cat > "$BATS_TEST_TMPDIR/prov.yml" <<'Y'
providers:
  github:
    tier_map:
      3: issue
    missing_tier_behavior: bogus-value
Y
    export LIFECYCLE_PROVIDERS_CONFIG="$BATS_TEST_TMPDIR/prov.yml"
    "$SCRIPT" init "org/repo#14" >/dev/null
    run "$SCRIPT" provision github__org_repo_14 --tier 1 --title "Init"
    [ "$status" -eq 2 ]   # errors, does not collapse to a label
}
@test "non-numeric --parent-tier fails with a curated error, not a traceback" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#15" >/dev/null
    run "$SCRIPT" provision github__org_repo_15 --tier 4 --title "x" --parent-tier abc
    [ "$status" -eq 64 ]; [[ "$output" == *"--parent-tier must be 1-4"* ]]
}
@test "partial failure -> FAILED_PROVISION; same-(tier,key) retry updates IN PLACE (no duplicate, FR-022)" {
    mk_provision_stub
    "$SCRIPT" init "org/repo#11" >/dev/null
    # 1st attempt fails (title contains FAIL); identity pinned by --key S9
    "$SCRIPT" provision github__org_repo_11 --tier 4 --key S9 --title "FAIL me" --parent-tier 3 >/dev/null 2>&1 || true
    run "$SCRIPT" status github__org_repo_11 --json
    [ "$(echo "$output" | tier_count 4)" = "1" ]
    [ "$(echo "$output" | tier_state 4)" = "FAILED_PROVISION" ]
    # retry SAME key, now-succeeding title -> in-place flip to present, still ONE tier-4 node
    run "$SCRIPT" provision github__org_repo_11 --tier 4 --key S9 --title "now ok" --parent-tier 3
    [ "$status" -eq 0 ]
    run "$SCRIPT" status github__org_repo_11 --json
    [ "$(echo "$output" | tier_count 4)" = "1" ]
    [ "$(echo "$output" | tier_state 4)" = "present" ]
}

# ============================================================================
# US4 — Jira via pre-authenticated Atlassian MCP (T028–T032, SC-004)
# ============================================================================

use_repo_config() { export LIFECYCLE_PROVIDERS_CONFIG="$BATS_TEST_DIRNAME/../../configs/claude/config/tracker_providers.yml"; }

@test "Jira entry detection: bare issue key -> jira provider" {
    run "$SCRIPT" init PROJ-123
    [ "$status" -eq 0 ]; [[ "$output" == *"provider=jira"* ]]
}
@test "Jira entry detection: browse URL -> jira provider + extracted key" {
    run "$SCRIPT" init "https://acme.atlassian.net/browse/ENG-44"
    [ "$status" -eq 0 ]; [[ "$output" == *"jira__ENG-44"* ]]
}
@test "status-map: Jira renders canonical status as a workflow TRANSITION (not a label, FR-021)" {
    use_repo_config
    run "$SCRIPT" status-map jira in-progress
    [ "$status" -eq 0 ]; [[ "$output" == transition* ]]; [[ "$output" == *"In Progress"* ]]
}
@test "status-map: GitHub renders canonical status as a label" {
    use_repo_config
    run "$SCRIPT" status-map github done
    [ "$status" -eq 0 ]; [[ "$output" == label* ]]; [[ "$output" == *"done"* ]]
}
@test "status-map: unknown status -> error (no silent default)" {
    use_repo_config
    run "$SCRIPT" status-map jira not-a-status
    [ "$status" -eq 2 ]
}
@test "SC-004: the identical lifecycle flow runs on a GitHub track (provider only differs)" {
    "$SCRIPT" init "org/repo#77" >/dev/null
    run "$SCRIPT" advance github__org_repo_77 --actor agent --gate '{"gate_type":"artifact","present":true}'
    [ "$status" -eq 0 ]; [[ "$output" == *"specify -> clarify"* ]]
    # same commands/gates as the jira tracks used throughout US1/US2 -> SC-004 holds
}
@test "GitHub URL entry parses to org/repo#N (regression: sed delimiter, not an empty track)" {
    run "$SCRIPT" init "https://github.com/acme/widgets/issues/42"
    [ "$status" -eq 0 ]; [[ "$output" == *"provider=github"* ]]; [[ "$output" == *"acme/widgets#42"* ]]
    run "$SCRIPT" status github__acme_widgets_42 --json
    [ "$status" -eq 0 ]
}
@test "GitLab URL entry parses to group/proj#N" {
    run "$SCRIPT" init "https://gitlab.com/acme/widgets/-/issues/9"
    [ "$status" -eq 0 ]; [[ "$output" == *"provider=gitlab"* ]]; [[ "$output" == *"acme/widgets#9"* ]]
}
@test "init refuses an entry that parses to an empty entity (no provider__ corruption)" {
    run "$SCRIPT" init "https://github.com/not-an-issue-url"
    [ "$status" -ne 0 ]
}
@test "status-map: Linear renders canonical status as a workflow STATE (transition), not a label" {
    use_repo_config
    run "$SCRIPT" status-map linear in-progress
    [ "$status" -eq 0 ]; [[ "$output" == transition* ]]; [[ "$output" == *"In Progress"* ]]
}

# ============================================================================
# US5 — review-gate verdict, loop-safe reconciliation, drift audit (T038,T040,T041)
# ============================================================================

@test "verdict: empty / NO_ISSUES -> APPROVED" {
    run bash -c "echo '[]' | '$SCRIPT' verdict --stdin"
    [ "$(echo "$output" | field verdict)" = "APPROVED" ]
    run bash -c "printf 'NO_ISSUES' | '$SCRIPT' verdict --stdin"
    [ "$(echo "$output" | field verdict)" = "APPROVED" ]
}
@test "verdict: a CRITICAL/HIGH finding -> BLOCKED" {
    run bash -c "echo '[{\"severity\":\"CRITICAL\",\"title\":\"x\"}]' | '$SCRIPT' verdict --stdin"
    [ "$(echo "$output" | field verdict)" = "BLOCKED" ]
}
@test "verdict: only low/medium findings -> NEEDS_REVIEW" {
    run bash -c "echo '[{\"severity\":\"LOW\",\"title\":\"nit\"}]' | '$SCRIPT' verdict --stdin"
    [ "$(echo "$output" | field verdict)" = "NEEDS_REVIEW" ]
}
@test "verdict: unparseable review -> BLOCKED (fail closed)" {
    run bash -c "printf 'garbage not json' | '$SCRIPT' verdict --stdin"
    [ "$(echo "$output" | field verdict)" = "BLOCKED" ]
}

@test "reconcile: first sync establishes shadow; same value again is a noop (no loop)" {
    use_repo_config
    "$SCRIPT" init PROJ-40 >/dev/null   # phase specify -> canonical planned
    run "$SCRIPT" reconcile jira__PROJ-40 --tracker-status planned
    [ "$status" -eq 0 ]
    run "$SCRIPT" reconcile jira__PROJ-40 --tracker-status planned
    [ "$status" -eq 0 ]; [[ "$output" == *"in sync"* ]]   # origin suppression: no ping-pong
}
@test "reconcile: tracker-side change is adopted (human moved the ticket)" {
    use_repo_config
    "$SCRIPT" init PROJ-41 >/dev/null
    "$SCRIPT" reconcile jira__PROJ-41 --tracker-status planned >/dev/null   # baseline
    run "$SCRIPT" reconcile jira__PROJ-41 --tracker-status done             # human changed it
    [ "$status" -eq 0 ]; [[ "$output" == *"adopted tracker status done"* ]]
}
@test "reconcile: after adopt, the SAME tracker value settles to noop (no oscillation, SC-010)" {
    use_repo_config
    "$SCRIPT" init PROJ-45 >/dev/null
    "$SCRIPT" reconcile jira__PROJ-45 --tracker-status planned >/dev/null   # baseline
    "$SCRIPT" reconcile jira__PROJ-45 --tracker-status done >/dev/null      # adopt
    run "$SCRIPT" reconcile jira__PROJ-45 --tracker-status done             # must NOT push back
    [ "$status" -eq 0 ]; [[ "$output" == *"in sync"* ]]
    run "$SCRIPT" reconcile jira__PROJ-45 --tracker-status done             # and stay settled
    [[ "$output" == *"in sync"* ]]
}
@test "reconcile: genuine conflict (both diverge to different values) -> needs-human" {
    use_repo_config
    "$SCRIPT" init PROJ-46 >/dev/null
    "$SCRIPT" reconcile jira__PROJ-46 --tracker-status planned >/dev/null   # baseline (shadow=planned, local=planned)
    # advance the lifecycle (local moves) AND have the tracker move elsewhere
    "$SCRIPT" advance jira__PROJ-46 --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
    "$SCRIPT" advance jira__PROJ-46 --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
    "$SCRIPT" advance jira__PROJ-46 --actor agent --gate '{"gate_type":"verdict","verdict":"APPROVED"}' >/dev/null  # now plan -> in-progress
    run "$SCRIPT" reconcile jira__PROJ-46 --tracker-status done
    [ "$status" -eq 1 ]; [[ "$output" == *"CONFLICT"* ]]
}
@test "audit: stale tracking state (shadow disagrees with lifecycle status) is flagged" {
    use_repo_config
    "$SCRIPT" init PROJ-47 >/dev/null
    "$SCRIPT" reconcile jira__PROJ-47 --tracker-status planned >/dev/null   # shadow=planned
    # advance so phase-derived status moves to in-progress while shadow stays planned
    "$SCRIPT" advance jira__PROJ-47 --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
    "$SCRIPT" advance jira__PROJ-47 --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null
    "$SCRIPT" advance jira__PROJ-47 --actor agent --gate '{"gate_type":"verdict","verdict":"APPROVED"}' >/dev/null
    run "$SCRIPT" audit jira__PROJ-47
    [ "$status" -eq 1 ]; [[ "$output" == *"stale tracking state"* ]]
}
@test "audit: a clean track reports no drift (exit 0)" {
    "$SCRIPT" init PROJ-42 >/dev/null
    run "$SCRIPT" audit jira__PROJ-42
    [ "$status" -eq 0 ]; [[ "$output" == *"no drift"* ]]
}
@test "audit: a non-exempt subtask without coverage past Implement is flagged (exit 1)" {
    "$SCRIPT" init PROJ-43 >/dev/null
    # advance to verify with one uncovered subtask via direct state (simulate drift)
    python3 - "$LIFECYCLE_STATE_DIR/jira__PROJ-43.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p))
d["current_phase"]="verify"
d["completed_phases"]=["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement"]
d["subtask_states"]={"S1":{"phase":"verify","exempt":False,"coverage_workflow_ids":[]}}
json.dump(d,open(p,"w"))
PY
    run "$SCRIPT" audit jira__PROJ-43
    [ "$status" -eq 1 ]; [[ "$output" == *"DRIFT"* ]]; [[ "$output" == *"no smoke coverage"* ]]
}
@test "audit: a skipped phase is flagged" {
    "$SCRIPT" init PROJ-44 >/dev/null
    python3 - "$LIFECYCLE_STATE_DIR/jira__PROJ-44.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p))
d["current_phase"]="plan"; d["completed_phases"]=["specify"]   # skipped clarify + spec_review_product
json.dump(d,open(p,"w"))
PY
    run "$SCRIPT" audit jira__PROJ-44
    [ "$status" -eq 1 ]; [[ "$output" == *"skipped phase"* ]]
}

# ============================================================================
# T027 — record lifecycle artifacts at their tier (FR-015)
# ============================================================================

@test "artifact: records an artifact on the Tier-3 entry node" {
    "$SCRIPT" init PROJ-50 >/dev/null
    run "$SCRIPT" artifact jira__PROJ-50 --tier 3 --path specs/365/plan.md --kind plan
    [ "$status" -eq 0 ]
    run "$SCRIPT" status jira__PROJ-50 --json
    [[ "$output" == *"plan.md"* ]]; [[ "$output" == *'"artifacts"'* ]]
}
@test "artifact: requires --tier and --path" {
    "$SCRIPT" init PROJ-51 >/dev/null
    run "$SCRIPT" artifact jira__PROJ-51 --path x
    [ "$status" -eq 64 ]
    run "$SCRIPT" artifact jira__PROJ-51 --tier 3
    [ "$status" -eq 64 ]
}
@test "artifact: a tier with no present node -> error (exit 1)" {
    "$SCRIPT" init PROJ-52 >/dev/null   # only the Tier-3 entry exists; no Tier-1 node
    run "$SCRIPT" artifact jira__PROJ-52 --tier 1 --path spec.md
    [ "$status" -eq 1 ]; [[ "$output" == *"no present tier-1 node"* ]]
}
