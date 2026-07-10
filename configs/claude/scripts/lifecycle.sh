#!/usr/bin/env bash
# lifecycle.sh — shared state machine for the codified, state-gated development lifecycle.
#
# Spec: specs/365-lifecycle-codification/ (contracts/lifecycle-cli.md is authoritative).
# Mirrors the merge_decision.sh / verification_gate.sh idiom (specs 360/361): a PURE,
# offline-testable `decide` core (signals JSON in -> {action} out, always exit 0, fails
# closed) plus thin stateful subcommands. The /lifecycle-run skill (humans, advisory) and the
# autodev loop (agents, hard halt) both consume this one tested gate.
#
# Subcommands:
#   init <entry-point>                 Parse provider/entity, create a track at phase 1.
#   status <track-id> [--json]         Report current phase, completed phases, gates.
#   decide [<signals-json>]            PURE: map signals -> {action,missing_prereq,reason}.
#   gate [<signals-json>]              decide + non-zero exit for loop callers.
#   advance <track-id> [--gate <json>] [--actor agent|human] [--override <reason>]
#   anchor <track-id>                  Re-emit the active phase (drift re-anchoring).
#   regress <track-id> --to <phase> --reason <text>
#
# State: ${LIFECYCLE_STATE_DIR:-${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state}
#        track-id == <provider>__<sanitized-entity-id>; files 0600 in a 0700 dir.

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "lifecycle: $*" >&2; else printf '%s\n' "lifecycle: $*" >&2; fi; }

STATE_DIR="${LIFECYCLE_STATE_DIR:-${MANIFEST_STATE_ROOT:-$HOME/.manifest}/lifecycle/state}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Injectable smoke-manage seam (FR-012: consume as-is). Default = deployed runtime.
SMOKE_CMD="${LIFECYCLE_SMOKE_CMD:-python3 ${HOME}/.claude/scripts/smoke_test.py}"
smoke() {
    local arr
    read -ra arr <<< "${SMOKE_CMD}"
    "${arr[@]}" "$@"
}

usage() {
    cat << 'USAGE'
Usage: lifecycle.sh <subcommand> [args]

  init <entry-point>        Create a track from a ticket URL/issue key (phase: specify).
  status <track-id> [--json]   Show current phase, completed phases, outstanding gates.
  decide [<signals-json>]   PURE gate: signals (arg/stdin) -> {action,missing_prereq,reason}.
                            action ∈ allow|warn|refuse. Always exits 0; malformed -> refuse.
  gate [<signals-json>]     Like decide but exits non-zero on warn(3)/refuse(1) for loops.
  advance <track-id> [--gate <json>] [--actor agent|human] [--override <reason>]
                            [--unit <smoke-app>] [--junit <path>]
                            implement/verify auto-compute the gate via the smoke runtime.
  subtask <track-id> --id <sid> [--ship <workflow-id>] [--exempt --reason <text>]
  provision <track-id> --tier <1-4> --title <t> [--parent-tier <m>] [--external-id <x>]
                            Top-down, create-or-adopt; missing tier => config error.
  status-map <provider> <canonical-status>
                            Render a canonical status as a provider label / Jira transition.
  verdict [--from <file>|--stdin]   Map a /spec-review --format json result to a gate signal.
  reconcile <track-id> --tracker-status <canonical>   Loop-safe status reconciliation.
  audit <track-id>          Surface lifecycle drift (skipped phase / missing coverage / failed node).
  artifact <track-id> --tier <1-4> --path <ref> [--kind <k>]   Record an artifact at its tier.
  anchor <track-id>         Re-print the active phase.
  regress <track-id> --to <phase> --reason <text>
USAGE
}

# Phase order is the single source for sequencing (matches the Lifecycle Definition).
PHASES="specify clarify spec_review_product plan task_creation analyze spec_review_tech implement verify"

# --- PURE decision core (no I/O, deterministic, always exit 0, fail-closed) -----------
DECIDE_PY='
import json, sys

PHASES = ["specify","clarify","spec_review_product","plan","task_creation",
          "analyze","spec_review_tech","implement","verify"]
ORDER = {p: i + 1 for i, p in enumerate(PHASES)}

raw = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "" else sys.stdin.read()

def out(action, reason, missing=None):
    print(json.dumps({"action": action, "missing_prereq": missing, "reason": reason}))
    sys.exit(0)

try:
    s = json.loads(raw)
except Exception:
    out("refuse", "unparseable signals — failing closed", None)

actor = s.get("actor_mode", "agent")
block = "refuse" if actor != "human" else "warn"   # human gets advisory; default strict

cur = s.get("current_phase")
if cur not in ORDER:
    out("refuse", "unknown or missing current_phase — failing closed", None)

req = s.get("requested_phase")
if req is None:
    req = PHASES[ORDER[cur]] if ORDER[cur] < len(PHASES) else cur   # default: next phase
if req not in ORDER:
    out("refuse", "unknown requested_phase — failing closed", None)

completed = set(s.get("completed_phases", []) or [])

# Skip detection: every phase before the requested one must be completed, except the
# current phase (whose exit gate is evaluated below). Catches jump-ahead automatically.
for p in PHASES:
    if ORDER[p] < ORDER[req] and p != cur and p not in completed:
        out(block, "phase %s must complete before %s" % (p, req), p)

# Gate evaluation of the phase being COMPLETED (cur).
gate = s.get("phase_gate", {}) or {}
gt = gate.get("gate_type", "artifact")

if gt == "verdict":
    v = gate.get("verdict")
    if v == "APPROVED":      out("allow", "review approved")
    if v == "NEEDS_REVIEW":  out("warn", "review needs attention (advisory)")
    if v == "BLOCKED":       out(block, "review blocked (Tier-1 / critical finding)")
    out("refuse", "verdict missing — failing closed")
elif gt == "runner":
    ec = gate.get("exit_code")
    if ec == 0:      out("allow", "verify suite passed")
    if ec == 1:      out(block, "verify suite failed/blocked")
    if ec == 2:      out(block, "verify EMPTY — missing coverage is not a pass")
    out("refuse", "exit_code missing/invalid — failing closed")
elif gt == "coverage":
    c = gate.get("coverage")
    if c == "OK":       out("allow", "all shipped user-facing workflows covered")
    if c == "MISSING":  out(block, "a shipped user-facing workflow lacks a smoke test")
    out("refuse", "coverage signal missing — failing closed")
elif gt == "artifact":
    present = gate.get("present")
    if present is True:   out("allow", "phase artifact present")
    if present is False:  out(block, "phase artifact missing")
    out("refuse", "artifact presence not asserted — failing closed")
else:
    out("refuse", "unknown gate_type — failing closed")
'

cmd_decide() { python3 -c "${DECIDE_PY}" "${1:-}"; }

cmd_gate() {
    local result action
    result="$(cmd_decide "${1:-}")"
    echo "${result}"
    action="$(printf '%s' "${result}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])')"
    case "${action}" in
        allow) return 0 ;;
        warn) return 3 ;;
        *) return 1 ;;
    esac
}

# --- entry-point detection (MVP: URL + key patterns) ----------------------------------
detect_provider() {
    # echoes "<provider> <entity-id>"; empty on no match.
    local ep="$1"
    case "${ep}" in
        *github.com/*/issues/*) echo "github $(echo "${ep}" | sed -E 's@.*github\.com/([^/]+/[^/]+)/issues/([0-9]+).*@\1#\2@')" ;;
        *gitlab.com/*/-/issues/*) echo "gitlab $(echo "${ep}" | sed -E 's@.*gitlab\.com/(.+)/-/issues/([0-9]+).*@\1#\2@')" ;;
        *linear.app/*) echo "linear $(echo "${ep}" | sed -E 's#.*/issue/([A-Z0-9]+-[0-9]+).*#\1#')" ;;
        *atlassian.net/browse/*) echo "jira $(echo "${ep}" | sed -E 's#.*/browse/([A-Z][A-Z0-9]+-[0-9]+).*#\1#')" ;;
        */*\#[0-9]*) echo "github ${ep}" ;;         # org/repo#42
        [A-Z][A-Z0-9]*-[0-9]*) echo "jira ${ep}" ;; # PROJ-123 (bare key -> jira)
        *) echo "" ;;
    esac
}

sanitize() { echo "$1" | tr '/#:' '___' | tr -cd 'A-Za-z0-9_.-'; }

track_path() { echo "${STATE_DIR}/$1.json"; }

ensure_state_dir() { [ -d "${STATE_DIR}" ] || {
    mkdir -p "${STATE_DIR}"
    chmod 700 "${STATE_DIR}"
}; }

read_track() {
    local p
    p="$(track_path "$1")"
    [ -f "${p}" ] || {
        err "no such track: $1"
        return 2
    }
    cat "${p}"
}

write_track() {
    # write_track <track-id> <json>  — atomic, 0600
    ensure_state_dir
    local p tmp
    p="$(track_path "$1")"
    tmp="${p}.tmp.$$"
    printf '%s\n' "$2" > "${tmp}"
    chmod 600 "${tmp}"
    mv "${tmp}" "${p}"
}

cmd_init() {
    local ep="${1:-}"
    [ -n "${ep}" ] || {
        err "init requires an entry point"
        return 64
    }
    local det provider entity
    det="$(detect_provider "${ep}")"
    provider="${det%% *}"
    entity="${det#* }"
    [ -n "${provider}" ] && [ -n "${entity}" ] && [ "${entity}" != "${provider}" ] ||
        {
            err "unrecognized or unparseable entry point: ${ep}"
            return 2
        }
    local track_id
    track_id="${provider}__$(sanitize "${entity}")"
    local p
    p="$(track_path "${track_id}")"
    if [ -f "${p}" ]; then
        echo "track exists: ${track_id} (phase: $(json_get "$(cat "${p}")" current_phase))"
        return 0
    fi
    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local json
    json="$(python3 -c '
import json,sys,uuid
tid,prov,ent,raw,now=sys.argv[1:6]
# Seed the entry entity as the present anchor Task (Tier 3) so descendants parent top-down
# and the anchor is never re-minted (FR-016: consume entry + provision missing descendants).
entry_node={"node_id":uuid.uuid4().hex,"tier_level":3,"key":ent,"external_id":ent,
 "construct":"entry","provider_type":prov,"parent_node_id":None,"parent_external_id":None,
 "provision_state":"present","status":"planned","remote_recorded_id":None,"source":"entry"}
print(json.dumps({"schema_version":1,"track_id":tid,
 "entry_point":{"raw":raw,"provider":prov,"entity_id":ent,"tier":3},
 "tier_anchor":"task","current_phase":"specify","completed_phases":[],
 "actor_mode":"human","regression_log":[],"subtask_states":{},
 "shipped_workflow_ids":[],"gate_results":{},"hierarchy":[entry_node],"created":now}))' \
        "${track_id}" "${provider}" "${entity}" "${ep}" "${now}")"
    write_track "${track_id}" "${json}"
    echo "initialized track: ${track_id} (provider=${provider}, entity=${entity}, phase=specify)"
}

json_get() { printf '%s' "$1" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('$2',''))"; }

cmd_status() {
    local id="${1:-}"
    [ -n "${id}" ] || {
        err "status requires a track-id"
        return 64
    }
    local j
    j="$(read_track "${id}")" || return $?
    if [ "${2:-}" = "--json" ]; then
        printf '%s\n' "${j}"
        return 0
    fi
    python3 -c '
import json,sys
PH=["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement","verify"]
d=json.load(sys.stdin); cur=d["current_phase"]; done=d.get("completed_phases",[])
i=PH.index(cur)
print("track:      %s"%d["track_id"])
print("provider:   %s (%s)"%(d["entry_point"]["provider"],d["entry_point"]["entity_id"]))
print("phase:      %d/9 %s"%(i+1,cur))
print("completed:  %s"%(", ".join(done) or "(none)"))
print("outstanding:%s"%(", ".join(PH[i:]) ))
rl=d.get("regression_log",[])
if rl: print("regressions:%d"%len(rl))
' <<< "${j}"
}

cmd_anchor() {
    local id="${1:-}"
    [ -n "${id}" ] || {
        err "anchor requires a track-id"
        return 64
    }
    local j
    j="$(read_track "${id}")" || return $?
    echo "[lifecycle] track ${id} is in phase: $(json_get "${j}" current_phase)"
}

# --- US2: smoke-backed Verify gate + Implement-exit coverage (FR-008..FR-012) -----------

# Manage per-Sub-Task state: --ship records a covering workflow id; --exempt marks a
# non-user-facing Sub-Task (rationale required). subtask_states[sid] + shipped_workflow_ids.
cmd_subtask() {
    local id="${1:-}"
    shift || true
    [ -n "${id}" ] || {
        err "subtask requires a track-id"
        return 64
    }
    local sid='' ship='' exempt='' reason=''
    while [ $# -gt 0 ]; do
        case "$1" in
            --id)
                sid="${2:-}"
                shift 2
                ;;
            --ship)
                ship="${2:-}"
                shift 2
                ;;
            --exempt)
                exempt=1
                shift
                ;;
            --reason)
                reason="${2:-}"
                shift 2
                ;;
            *)
                err "subtask: unknown option $1"
                return 64
                ;;
        esac
    done
    [ -n "${sid}" ] || {
        err "subtask requires --id"
        return 64
    }
    [ -z "${exempt}" ] || [ -n "${reason}" ] || {
        err "subtask --exempt requires --reason (FR-011)"
        return 2
    }
    local j
    j="$(read_track "${id}")" || return $?
    local updated
    updated="$(python3 -c '
import json,sys
j=json.loads(sys.argv[1]); sid,ship,exempt,reason=sys.argv[2:6]
st=j.setdefault("subtask_states",{}).setdefault(sid,{"phase":"implement","exempt":False,"coverage_workflow_ids":[]})
if exempt=="1":
    st["exempt"]=True; st["exempt_reason"]=reason
if ship:
    if ship not in st["coverage_workflow_ids"]: st["coverage_workflow_ids"].append(ship)
    if ship not in j.setdefault("shipped_workflow_ids",[]): j["shipped_workflow_ids"].append(ship)
print(json.dumps(j))' "${j}" "${sid}" "${ship}" "${exempt}" "${reason}")"
    write_track "${id}" "${updated}"
    echo "subtask ${sid}: $([ -n "${exempt}" ] && echo exempt || echo "ship=${ship:-<none>}")"
}

# Coverage signal for the Implement-exit gate: every non-exempt Sub-Task needs >=1 covering
# workflow, and every shipped workflow id must exist in the smoke catalog (FR-008/FR-010).
# Fails CLOSED: any error (smoke missing, malformed/unexpected output) -> MISSING, never a crash.
# The real `smoke list --json` returns a per-app dict {app:[{id,...}]}; a flat list is tolerated.
compute_coverage_signal() {
    local j="$1" unit="$2" catalog
    catalog="$(smoke list --app "${unit}" --json 2> /dev/null || echo '{}')"
    python3 -c '
import json, sys
def out(cov, **kw):
    d = {"gate_type": "coverage", "coverage": cov}; d.update(kw)
    print(json.dumps(d)); sys.exit(0)
try:
    j = json.loads(sys.argv[1]); cat = json.loads(sys.argv[2] or "{}")
except Exception:
    out("MISSING", reason="unparseable smoke catalog — failing closed")
if isinstance(cat, dict):
    recs = [r for v in cat.values() if isinstance(v, list) for r in v]
elif isinstance(cat, list):
    recs = cat
else:
    out("MISSING", reason="unexpected smoke catalog shape — failing closed")
cat_ids = {c.get("id") for c in recs if isinstance(c, dict)}
required = set(j.get("shipped_workflow_ids", []))
for sid, st in (j.get("subtask_states") or {}).items():
    if st.get("exempt"):
        if not st.get("exempt_reason"):
            out("MISSING", reason="exempt subtask %s lacks rationale" % sid)
        continue
    wfs = st.get("coverage_workflow_ids", [])
    if not wfs:
        out("MISSING", reason="subtask %s has no smoke test" % sid)
    required |= set(wfs)
missing = sorted(required - cat_ids)
out("MISSING" if missing else "OK", missing=missing)
' "${j}" "${catalog}"
}

# Runner signal for the Verify gate: run the suite at Lite, gate on exit code (0/1/2).
# stderr is kept (not discarded) in a sibling .log so exit 2 from an infra/usage error is
# diagnosable rather than silently read as "missing coverage".
compute_verify_signal() {
    local unit="$1" junit="$2" ec=0
    smoke run --app "${unit}" --tier Lite --junit "${junit}" > /dev/null 2> "${junit%.xml}.log" || ec=$?
    [ "${ec}" -eq 0 ] || err "smoke run exited ${ec} (diagnostics: ${junit%.xml}.log)"
    echo "{\"gate_type\":\"runner\",\"exit_code\":${ec}}"
}

# T021/FR-011: the workflow ids whose JUnit <testcase> passed (no failure/error/skipped),
# recorded back into each Sub-Task for per-Sub-Task verification traceability.
junit_passed_ids() {
    local junit="$1"
    [ -f "${junit}" ] || {
        echo '[]'
        return 0
    }
    python3 -c '
import sys, json, xml.etree.ElementTree as ET
try:
    data = open(sys.argv[1], "rb").read()
    dl = data.lower()
    # Defense-in-depth (no defusedxml dep): refuse DTDs/entities to block XXE and
    # billion-laughs. Our smoke JUnit never declares them; an attacker-supplied one would.
    if b"<!doctype" in dl or b"<!entity" in dl:
        print("[]"); sys.exit(0)
    root = ET.fromstring(data)
    ids = [tc.get("name") for tc in root.iter("testcase")
           if tc.get("name") and not any(c.tag in ("failure","error","skipped") for c in tc)]
    print(json.dumps(ids))
except Exception:
    print("[]")
' "${junit}" 2> /dev/null || echo '[]'
}

cmd_advance() {
    local id="${1:-}"
    shift || true
    [ -n "${id}" ] || {
        err "advance requires a track-id"
        return 64
    }
    local gate_json='' actor='' override='' unit='' junit='' verified_ids='[]'
    while [ $# -gt 0 ]; do
        case "$1" in
            --gate)
                gate_json="${2:-}"
                shift 2
                ;;
            --actor)
                actor="${2:-}"
                shift 2
                ;;
            --override)
                override="${2:-}"
                shift 2
                ;;
            --unit)
                unit="${2:-}"
                shift 2
                ;;
            --junit)
                junit="${2:-}"
                shift 2
                ;;
            *)
                err "advance: unknown option $1"
                return 64
                ;;
        esac
    done
    local j
    j="$(read_track "${id}")" || return $?
    local cur
    cur="$(json_get "${j}" current_phase)"
    # US2: auto-compute the gate for the smoke-backed phases when not explicitly supplied.
    if [ -z "${gate_json}" ]; then
        case "${cur}" in
            implement)
                [ -n "${unit}" ] || {
                    err "advance implement requires --unit <smoke-app> (or --gate)"
                    return 64
                }
                gate_json="$(compute_coverage_signal "${j}" "${unit}")"
                ;;
            verify)
                [ -n "${unit}" ] || {
                    err "advance verify requires --unit <smoke-app> (or --gate)"
                    return 64
                }
                [ -n "${junit}" ] || junit="${STATE_DIR}/${id}.verify.xml"
                gate_json="$(compute_verify_signal "${unit}" "${junit}")"
                verified_ids="$(junit_passed_ids "${junit}")"
                ;;
            *) gate_json='{}' ;;
        esac
    fi
    [ -n "${actor}" ] || actor="$(json_get "${j}" actor_mode)"
    # assemble signals for the pure core
    local signals
    signals="$(python3 -c '
import json,sys
j=json.loads(sys.argv[1]); gate=json.loads(sys.argv[2] or "{}"); actor=sys.argv[3]
print(json.dumps({"actor_mode":actor,"current_phase":j["current_phase"],
 "completed_phases":j.get("completed_phases",[]),"phase_gate":gate}))' \
        "${j}" "${gate_json}" "${actor}")"
    local decision action
    decision="$(cmd_decide "${signals}")"
    action="$(json_get "${decision}" action)"
    case "${action}" in
        allow) : ;;
        warn)
            if [ -n "${override}" ]; then
                err "advisory: $(json_get "${decision}" reason) — overridden: ${override}"
            else
                err "advisory warning: $(json_get "${decision}" reason) (re-run with --override <reason> to proceed)"
                return 3
            fi
            ;;
        *)
            err "refused: $(json_get "${decision}" reason) (missing: $(json_get "${decision}" missing_prereq))"
            return 1
            ;;
    esac
    # advance: append cur to completed, set next phase, record gate result, and (FR-028)
    # transition per-Sub-Task sub-states as the Task crosses Implement -> Verify -> done.
    local updated
    updated="$(python3 -c '
import json,sys
j=json.loads(sys.argv[1]); ov=sys.argv[2]; decision=json.loads(sys.argv[3] or "{}")
gate=json.loads(sys.argv[4] or "{}"); verified=set(json.loads(sys.argv[5] or "[]"))
PH=["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement","verify"]
cur=j["current_phase"]; i=PH.index(cur)
if cur not in j["completed_phases"]: j["completed_phases"].append(cur)
nxt = PH[i+1] if i < len(PH)-1 else "done"
j["current_phase"]=nxt
j.pop("status_override",None)   # a phase move re-establishes the phase-derived canonical status
j.setdefault("gate_results",{})[cur]={"decision":decision.get("action"),"gate":gate}
# Two-level iterator (FR-028): Sub-Tasks ride the Task through phases 8-9.
subs=j.get("subtask_states") or {}
if cur=="implement":
    for sid,st in subs.items():
        if not st.get("exempt"): st["phase"]="verify"
elif cur=="verify":
    for sid,st in subs.items():
        st["phase"]="done"
        # T021/FR-011: record which declared workflows actually passed in this run.
        st["verified_workflow_ids"]=[w for w in st.get("coverage_workflow_ids",[]) if w in verified]
if ov: j.setdefault("regression_log",[]).append({"override":ov,"at_phase":cur})
print(json.dumps(j))' "${j}" "${override}" "${decision}" "${gate_json}" "${verified_ids}")"
    write_track "${id}" "${updated}"
    echo "advanced ${id}: ${cur} -> $(json_get "${updated}" current_phase)"
}

cmd_regress() {
    local id="${1:-}"
    shift || true
    [ -n "${id}" ] || {
        err "regress requires a track-id"
        return 64
    }
    local to='' reason=''
    while [ $# -gt 0 ]; do
        case "$1" in
            --to)
                to="${2:-}"
                shift 2
                ;;
            --reason)
                reason="${2:-}"
                shift 2
                ;;
            *)
                err "regress: unknown option $1"
                return 64
                ;;
        esac
    done
    [ -n "${reason}" ] || {
        err "regress requires --reason"
        return 2
    }
    case " ${PHASES} " in *" ${to} "*) : ;; *)
        err "regress: unknown phase: ${to}"
        return 2
        ;;
    esac
    local j
    j="$(read_track "${id}")" || return $?
    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local updated
    updated="$(python3 -c '
import json,sys
j=json.loads(sys.argv[1]); to=sys.argv[2]; reason=sys.argv[3]; now=sys.argv[4]
PH=["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement","verify"]
frm=j["current_phase"]
j.setdefault("regression_log",[]).append({"from":frm,"to":to,"reason":reason,"ts":now})
j["completed_phases"]=[p for p in j.get("completed_phases",[]) if PH.index(p)<PH.index(to)]
j["current_phase"]=to
print(json.dumps(j))' "${j}" "${to}" "${reason}" "${now}")"
    write_track "${id}" "${updated}"
    echo "regressed ${id}: -> ${to} (${reason})"
}

# --- US3: four-tier hierarchy provisioning (FR-013..FR-017) -----------------------------

LIFECYCLE_PROVIDERS_CONFIG="${LIFECYCLE_PROVIDERS_CONFIG:-${HOME}/.claude/config/lifecycle_providers.yml}"

# Provider tool seam: create ONE remote node, echo its external id; non-zero = failure.
# args: <provider> <construct> <title> <parent-external-id-or-empty>. Real backends route to
# git_ops.sh (gh/glab), linear_ops.sh, or the Atlassian MCP (US4); tests inject a stub.
provision_remote() {
    if [ -n "${LIFECYCLE_PROVISION_CMD:-}" ]; then
        local arr
        read -ra arr <<< "${LIFECYCLE_PROVISION_CMD}"
        "${arr[@]}" "$@"
        return $?
    fi
    # T025: default concrete backends. args: <provider> <construct> <title> <parent-ext>.
    # github/gitlab via git_ops.sh (gh/glab passthrough); linear via linear_ops.sh; jira is
    # agent-layer (Atlassian MCP createJiraIssue) so the agent passes --external-id instead.
    # NOTE: exercised against real trackers in integration (not offline bats); Tier-1/2
    # constructs (Project V2 / Milestone / Epic) beyond Issue/Sub-Issue need provider-specific
    # handling not yet in git_ops.sh — those fall back to FAILED_PROVISION for reconciliation.
    local provider="$1" title="$3" parent="$4" out
    case "${provider}" in
        github | gitlab)
            out="$("${SCRIPT_DIR}/git_ops.sh" issue-create --title "${title}" 2> /dev/null)" || return 1
            printf '%s' "${out}" | grep -oE '[0-9]+$' | head -1
            ;;
        linear)
            if [ -n "${parent}" ]; then
                out="$("${SCRIPT_DIR}/linear_ops.sh" create-sub-issue --parent "${parent}" --title "${title}" 2> /dev/null)" || return 1
            else
                out="$("${SCRIPT_DIR}/linear_ops.sh" issue-create --title "${title}" 2> /dev/null)" || return 1
            fi
            printf '%s' "${out}" | grep -oE '[A-Z]+-[0-9]+' | head -1
            ;;
        jira)
            err "jira provisioning is agent-layer (Atlassian MCP createJiraIssue) — pass --external-id with the created key"
            return 70
            ;;
        *)
            err "no provisioning backend for provider: ${provider}"
            return 70
            ;;
    esac
}

# Resolve a tier -> native construct from config. Echoes the construct, or ERR:* / MISSING:<behavior>.
resolve_tier_construct() {
    local provider="$1" tier="$2"
    [ -f "${LIFECYCLE_PROVIDERS_CONFIG}" ] || {
        echo "ERR:no-config"
        return 0
    }
    python3 -c '
import sys, json
try:
    import yaml
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception:
    print("ERR:unreadable-config"); sys.exit(0)
p = (cfg.get("providers") or {}).get(sys.argv[2])
if not p:
    print("ERR:unknown-provider"); sys.exit(0)
c = (p.get("tier_map") or {}).get(int(sys.argv[3]))
print(str(c) if c is not None else "MISSING:%s" % p.get("missing_tier_behavior", "error"))
' "${LIFECYCLE_PROVIDERS_CONFIG}" "${provider}" "${tier}"
}

# provision <track-id> --tier N --title T [--key K] [--parent-tier M] [--parent-id P] [--external-id X]
# Top-down, create-or-adopt by stable (tier,key,parent), adjacency-checked, missing-tier ->
# config error, partial -> FAILED_PROVISION (in-place reattempt, no duplicates).
cmd_provision() {
    local id="${1:-}"
    shift || true
    [ -n "${id}" ] || {
        err "provision requires a track-id"
        return 64
    }
    local tier='' title='' parent_tier='' parent_id='' ext='' key=''
    while [ $# -gt 0 ]; do
        case "$1" in
            --tier)
                tier="${2:-}"
                shift 2
                ;;
            --title)
                title="${2:-}"
                shift 2
                ;;
            --parent-tier)
                parent_tier="${2:-}"
                shift 2
                ;;
            --parent-id)
                parent_id="${2:-}"
                shift 2
                ;;
            --external-id)
                ext="${2:-}"
                shift 2
                ;;
            --key)
                key="${2:-}"
                shift 2
                ;;
            *)
                err "provision: unknown option $1"
                return 64
                ;;
        esac
    done
    case "${tier}" in 1 | 2 | 3 | 4) : ;; *)
        err "provision requires --tier <1-4>"
        return 64
        ;;
    esac
    case "${parent_tier}" in '' | 1 | 2 | 3 | 4) : ;; *)
        err "provision --parent-tier must be 1-4"
        return 64
        ;;
    esac
    [ -n "${title}" ] || [ -n "${ext}" ] || [ -n "${key}" ] || {
        err "provision requires --title, --key, or --external-id"
        return 64
    }
    if [ -n "${parent_tier}" ] && [ "$((tier - 1))" -ne "${parent_tier}" ]; then
        err "tier ${tier} parent must be tier $((tier - 1)), not ${parent_tier} (adjacency, data-model)"
        return 2
    fi
    local j
    j="$(read_track "${id}")" || return $?
    local provider
    provider="$(printf '%s' "${j}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["entry_point"]["provider"])')"
    local construct
    construct="$(resolve_tier_construct "${provider}" "${tier}")"
    case "${construct}" in
        ERR:*)
            err "provider config error: ${construct#ERR:} (${LIFECYCLE_PROVIDERS_CONFIG})"
            return 2
            ;;
        MISSING:collapse-to-label) construct="label:tier${tier}" ;; # the ONLY declared fallback
        MISSING:*)
            err "tier ${tier} has no native construct on ${provider}; missing-tier=${construct#MISSING:} (FR-014)"
            return 2
            ;;
    esac
    key="${key:-${ext:-${title}}}"
    # Plan: resolve parent once (top-down + ambiguity), detect adopt/reattempt by (tier,key,parent).
    local plan
    plan="$(printf '%s' "${j}" | python3 -c '
import json,sys
j=json.load(sys.stdin); tier=int(sys.argv[1]); key=sys.argv[2]; ptier=sys.argv[3]; pid=sys.argv[4]
H=j.get("hierarchy") or []
parent_node_id=None; parent_ext=None
if ptier:
    pres=[n for n in H if n["tier_level"]==int(ptier) and n.get("provision_state")=="present"]
    if not pres:
        print(json.dumps({"action":"error","reason":"parent tier %s not provisioned (top-down required, FR-016)"%ptier})); sys.exit(0)
    if pid:
        pres=[n for n in pres if pid in (n.get("node_id"),n.get("key"),n.get("external_id"))]
        if not pres:
            print(json.dumps({"action":"error","reason":"no present tier-%s parent matches --parent-id %s"%(ptier,pid)})); sys.exit(0)
    elif len(pres)>1:
        print(json.dumps({"action":"error","reason":"ambiguous parent: %d present nodes at tier %s (use --parent-id)"%(len(pres),ptier)})); sys.exit(0)
    parent_node_id=pres[0].get("node_id"); parent_ext=pres[0].get("external_id")
for n in H:
    if n["tier_level"]==tier and n.get("key")==key and n.get("parent_node_id")==parent_node_id:
        if n.get("provision_state")=="present":
            print(json.dumps({"action":"adopt","external_id":n.get("external_id")})); sys.exit(0)
        print(json.dumps({"action":"reattempt","node_id":n.get("node_id"),"parent_node_id":parent_node_id,"parent_ext":parent_ext})); sys.exit(0)
print(json.dumps({"action":"create","parent_node_id":parent_node_id,"parent_ext":parent_ext}))
' "${tier}" "${key}" "${parent_tier}" "${parent_id}")"
    case "$(json_get "${plan}" action)" in
        adopt)
            echo "adopt tier ${tier} (${key}): $(json_get "${plan}" external_id) (idempotent)"
            return 0
            ;;
        error)
            err "$(json_get "${plan}" reason)"
            return 1
            ;;
    esac
    local parent_ext new_ext rc=0
    parent_ext="$(json_get "${plan}" parent_ext)"
    if [ -n "${ext}" ]; then
        new_ext="${ext}" # caller supplied an existing remote id -> adopt it
    else
        new_ext="$(provision_remote "${provider}" "${construct}" "${title:-${key}}" "${parent_ext}")" || rc=$?
    fi
    # Commit: upsert by node_id (reattempt reuses it; create mints a uuid). One row per (tier,key,parent).
    local updated
    updated="$(printf '%s' "${j}" | python3 -c '
import json,sys,uuid
j=json.load(sys.stdin); tier=int(sys.argv[1]); key=sys.argv[2]; construct=sys.argv[3]
new_ext=sys.argv[4]; rc=int(sys.argv[5]); plan=json.loads(sys.argv[6])
prov=j["entry_point"]["provider"]; H=j.setdefault("hierarchy",[])
nid=plan.get("node_id") or uuid.uuid4().hex
node=next((n for n in H if n.get("node_id")==nid), None)
if node is None: node={"node_id":nid}; H.append(node)
ok=(rc==0 and bool(new_ext))
node.update({"tier_level":tier,"key":key,"construct":construct,"provider_type":prov,
 "parent_node_id":plan.get("parent_node_id"),"parent_external_id":plan.get("parent_ext"),"status":"planned",
 "external_id": new_ext if ok else None,
 "remote_recorded_id": None if ok else (new_ext or None),
 "provision_state": "present" if ok else "FAILED_PROVISION"})
print(json.dumps(j))' "${tier}" "${key}" "${construct}" "${new_ext}" "${rc}" "${plan}")"
    write_track "${id}" "${updated}"
    if [ "${rc}" -ne 0 ] || [ -z "${new_ext}" ]; then
        err "provisioning failed for tier ${tier} (${construct}); node marked FAILED_PROVISION (FR-016)"
        return 1
    fi
    echo "provisioned tier ${tier} (${construct}): ${new_ext}"
}

# --- US4: provider status rendering (FR-021) -------------------------------------------
# status-map <provider> <canonical-status> -> "<kind>\t<rendering>" (kind from status_via).
# Jira/Linear render as a workflow TRANSITION/state (Jira ids resolved at runtime via the
# Atlassian MCP getTransitionsForJiraIssue, never free-text); GitHub/GitLab render as a label.
cmd_status_map() {
    local provider="${1:-}" canonical="${2:-}"
    [ -n "${provider}" ] && [ -n "${canonical}" ] || {
        err "status-map requires <provider> <canonical-status>"
        return 64
    }
    [ -f "${LIFECYCLE_PROVIDERS_CONFIG}" ] || {
        err "no providers config (${LIFECYCLE_PROVIDERS_CONFIG})"
        return 2
    }
    python3 -c '
import sys
try:
    import yaml; cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception: sys.exit(2)
p = (cfg.get("providers") or {}).get(sys.argv[2])
if not p: sys.exit(2)
val = (p.get("status_map") or {}).get(sys.argv[3])
if val is None: sys.exit(2)
print("%s\t%s" % (p.get("status_via", "label"), val))
' "${LIFECYCLE_PROVIDERS_CONFIG}" "${provider}" "${canonical}" ||
        {
            err "status-map: no mapping for ${provider}/${canonical}"
            return 2
        }
}

# --- US5: review-gate verdict, loop-safe reconciliation, drift audit (FR-021,FR-026,FR-027) ---

phase_canonical() {
    python3 -c '
import sys
try:
    import yaml; m=(yaml.safe_load(open(sys.argv[1])) or {}).get("phase_to_canonical_status") or {}
    print(m.get(sys.argv[2],"in-progress"))
except Exception:
    print("in-progress")
' "${LIFECYCLE_PROVIDERS_CONFIG}" "$1"
}

# verdict [--from <file>|--stdin]: map a /spec-review --format json result to a gate signal
# (FR-027). [] / NO_ISSUES -> APPROVED; any critical/high finding -> BLOCKED; else NEEDS_REVIEW.
cmd_verdict() {
    local src
    case "${1:-}" in
        --from) src="$(cat "${2:?--from needs a file}")" ;;
        --stdin | '') src="$(cat)" ;;
        *)
            err "verdict: use --from <file> or --stdin"
            return 64
            ;;
    esac
    printf '%s' "${src}" | python3 -c '
import json,sys
def out(v): print(json.dumps({"gate_type":"verdict","verdict":v})); sys.exit(0)
raw=sys.stdin.read().strip()
if raw in ("","[]","NO_ISSUES"): out("APPROVED")
try: data=json.loads(raw)
except Exception: out("BLOCKED")             # unparseable review -> fail closed
if isinstance(data,list): findings=data
elif isinstance(data,dict):
    findings=data.get("findings")
    if findings is None: out("BLOCKED")      # unrecognized envelope -> fail closed
else: out("BLOCKED")
if not findings: out("APPROVED")
def blocking(f):
    if isinstance(f,dict):
        if f.get("blocking") is True: return True
        return str(f.get("severity","")).upper() in ("CRITICAL","BLOCKED","BLOCKER","HIGH")
    # real spec_review.sh --format json emits findings as opaque strings; scan the blob for
    # blocking markers (structured severity comes with the T036 --format json upgrade).
    s=str(f).upper()
    return any(k in s for k in ("CRITICAL","BLOCKED","BLOCKER","TIER-1","TIER 1"))
out("BLOCKED" if any(blocking(f) for f in findings) else "NEEDS_REVIEW")
'
}

# reconcile <track-id> --tracker-status <canonical>: three-way shadow-compare with origin
# suppression (FR-021, SC-010). Adopts a tracker-side change; pushes a local change; flags a
# true conflict for a human. After a sync the shadow == synced value, so our own echo is a noop.
cmd_reconcile() {
    local id="${1:-}"
    shift || true
    [ -n "${id}" ] || {
        err "reconcile requires a track-id"
        return 64
    }
    local tracker=''
    while [ $# -gt 0 ]; do case "$1" in
        --tracker-status)
            tracker="${2:-}"
            shift 2
            ;;
        *)
            err "reconcile: unknown option $1"
            return 64
            ;;
    esac done
    [ -n "${tracker}" ] || {
        err "reconcile requires --tracker-status <canonical>"
        return 64
    }
    local j
    j="$(read_track "${id}")" || return $?
    # local canonical = an adopted-status override (a human tracker move) if present, else the
    # phase-derived status. The override is what stops the adopt path from oscillating: after an
    # adopt, local==shadow==tracker, so the next tick is a noop. cmd_advance clears it on a phase move.
    local override localc
    override="$(json_get "${j}" status_override)"
    if [ -n "${override}" ]; then localc="${override}"; else localc="$(phase_canonical "$(json_get "${j}" current_phase)")"; fi
    local result
    result="$(printf '%s' "${j}" | python3 -c '
import json,sys
j=json.load(sys.stdin); localc=sys.argv[1]; tracker=sys.argv[2]
shadow=(j.get("tracker_shadow") or {}).get("last_synced_status")
if shadow is None:
    action="noop" if localc==tracker else "push"; new=localc
elif tracker==shadow and localc==shadow: action="noop"; new=shadow
elif tracker!=shadow and localc==shadow: action="adopt"; new=tracker
elif localc!=shadow and tracker==shadow: action="push"; new=localc
elif localc==tracker: action="noop"; new=localc           # both moved to the SAME value -> resync, not a conflict
else: action="conflict"; new=shadow
print(json.dumps({"action":action,"new_shadow":new,"local":localc,"tracker":tracker}))
' "${localc}" "${tracker}")"
    local action
    action="$(json_get "${result}" action)"
    if [ "${action}" != "conflict" ]; then
        local updated
        updated="$(printf '%s' "${j}" | python3 -c '
import json,sys
j=json.load(sys.stdin); action=sys.argv[1]; ns=sys.argv[2]
j["tracker_shadow"]={"last_synced_status":ns}
if action=="adopt": j["status_override"]=ns   # local now mirrors the human tracker move
print(json.dumps(j))' "${action}" "$(json_get "${result}" new_shadow)")"
        write_track "${id}" "${updated}"
    fi
    case "${action}" in
        noop) echo "reconcile ${id}: in sync (${tracker})" ;;
        adopt) echo "reconcile ${id}: adopted tracker status ${tracker}" ;;
        push) echo "reconcile ${id}: local $(json_get "${result}" local) -> apply to tracker via status-map" ;;
        conflict)
            err "reconcile ${id}: CONFLICT (local=$(json_get "${result}" local), tracker=${tracker}) — needs-human"
            return 1
            ;;
    esac
}

# audit <track-id>: surface lifecycle drift (FR-026) — skipped phase, missing required smoke
# coverage past Implement, or a FAILED_PROVISION node pending reconciliation. Exit 1 if any.
cmd_audit() {
    local id="${1:-}"
    [ -n "${id}" ] || {
        err "audit requires a track-id"
        return 64
    }
    local j
    j="$(read_track "${id}")" || return $?
    local override localc
    override="$(json_get "${j}" status_override)"
    if [ -n "${override}" ]; then localc="${override}"; else localc="$(phase_canonical "$(json_get "${j}" current_phase)")"; fi
    printf '%s' "${j}" | python3 -c '
import json,sys
PH=["specify","clarify","spec_review_product","plan","task_creation","analyze","spec_review_tech","implement","verify"]
j=json.load(sys.stdin); localc=sys.argv[1]; f=[]
cur=j.get("current_phase"); done=set(j.get("completed_phases",[]))
ci=PH.index(cur) if cur in PH else len(PH)
for p in PH[:ci]:
    if p not in done: f.append("skipped phase: %s incomplete but current is %s"%(p,cur))
if cur in ("verify","done") or "implement" in done:
    for sid,st in (j.get("subtask_states") or {}).items():
        if st.get("exempt"):
            if not st.get("exempt_reason"): f.append("exempt subtask %s lacks rationale"%sid)
        elif not st.get("coverage_workflow_ids"):
            f.append("subtask %s has no smoke coverage"%sid)
for n in (j.get("hierarchy") or []):
    if n.get("provision_state")=="FAILED_PROVISION":
        f.append("hierarchy tier-%s %s is FAILED_PROVISION (needs reconciliation)"%(n.get("tier_level"),n.get("key")))
shadow=(j.get("tracker_shadow") or {}).get("last_synced_status")
if shadow is not None and shadow != localc:
    f.append("stale tracking state: tracker shadow=%s but lifecycle status=%s (run reconcile)"%(shadow,localc))
if f:
    for x in f: print("DRIFT: %s"%x)
    sys.exit(1)
print("no drift: track is consistent")
' "${localc}"
}

# artifact <track-id> --tier N --path <ref> [--kind <k>]: record a lifecycle artifact at its
# tier (FR-015: scope @ Initiative/Epic, design @ Task, impl/verify @ Sub-Task). Attaches to the
# present node at that tier (the entry node is the Tier-3 anchor).
cmd_artifact() {
    local id="${1:-}"
    shift || true
    [ -n "${id}" ] || {
        err "artifact requires a track-id"
        return 64
    }
    local tier='' path='' kind='ref'
    while [ $# -gt 0 ]; do case "$1" in
        --tier)
            tier="${2:-}"
            shift 2
            ;;
        --path)
            path="${2:-}"
            shift 2
            ;;
        --kind)
            kind="${2:-}"
            shift 2
            ;;
        *)
            err "artifact: unknown option $1"
            return 64
            ;;
    esac done
    case "${tier}" in 1 | 2 | 3 | 4) : ;; *)
        err "artifact requires --tier <1-4>"
        return 64
        ;;
    esac
    [ -n "${path}" ] || {
        err "artifact requires --path <ref>"
        return 64
    }
    local j
    j="$(read_track "${id}")" || return $?
    local updated
    updated="$(printf '%s' "${j}" | python3 -c '
import json,sys
j=json.load(sys.stdin); tier=int(sys.argv[1]); path=sys.argv[2]; kind=sys.argv[3]
H=j.get("hierarchy") or []
node=next((n for n in H if n["tier_level"]==tier and n.get("provision_state")=="present"), None)
if node is None:
    print(json.dumps({"_error":"no present tier-%d node to attach the artifact to"%tier})); sys.exit(0)
arts=node.setdefault("artifacts",[]); e={"kind":kind,"path":path}
if e not in arts: arts.append(e)
print(json.dumps(j))' "${tier}" "${path}" "${kind}")"
    if printf '%s' "${updated}" | grep -q '"_error"'; then
        err "$(json_get "${updated}" _error)"
        return 1
    fi
    write_track "${id}" "${updated}"
    echo "artifact recorded at tier ${tier}: ${kind}=${path}"
}

main() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
        --help | -h | help)
            usage
            exit 0
            ;;
        init) cmd_init "$@" ;;
        status-map) cmd_status_map "$@" ;;
        verdict) cmd_verdict "$@" ;;
        reconcile) cmd_reconcile "$@" ;;
        audit) cmd_audit "$@" ;;
        artifact) cmd_artifact "$@" ;;
        status) cmd_status "$@" ;;
        decide)
            cmd_decide "${1:-}"
            exit 0
            ;;
        gate) cmd_gate "${1:-}" ;;
        advance) cmd_advance "$@" ;;
        subtask) cmd_subtask "$@" ;;
        provision) cmd_provision "$@" ;;
        anchor) cmd_anchor "$@" ;;
        regress) cmd_regress "$@" ;;
        *)
            err "unknown subcommand: ${sub:-<none>}"
            usage >&2
            exit 64
            ;;
    esac
}

main "$@"
