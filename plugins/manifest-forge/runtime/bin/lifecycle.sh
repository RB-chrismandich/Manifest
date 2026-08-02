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
# State: $XDG_STATE_HOME/manifest/forge/lifecycle
#        track-id == <provider>__<sanitized-entity-id>; files 0600 in a 0700 dir.

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "lifecycle: $*" >&2; else printf '%s\n' "lifecycle: $*" >&2; fi; }

FORGE_RUNTIME_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
FORGE_CONFIG_DIR="$FORGE_RUNTIME_DIR/config"
XDG_STATE_ROOT="${XDG_STATE_HOME:-${HOME}/.local/state}"
FORGE_STATE_DIR="${XDG_STATE_ROOT}/manifest/forge"
export FORGE_RUNTIME_DIR FORGE_CONFIG_DIR FORGE_STATE_DIR
STATE_DIR="${FORGE_STATE_DIR}/lifecycle"
SCRIPT_DIR="$FORGE_RUNTIME_DIR/bin"
STATE_PATH_VALIDATOR="${FORGE_RUNTIME_DIR}/python/lifecycle_state.py"

# Smoke execution is an explicit argv seam; the Forge bundle never traverses
# into another plugin or guesses a harness-global executable path.
SMOKE_CMD="${LIFECYCLE_SMOKE_CMD:-}"
smoke() {
    local arr
    [[ -n "${SMOKE_CMD}" ]] || {
        err "LIFECYCLE_SMOKE_CMD is required for smoke-backed lifecycle gates"
        return 69
    }
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
export SCRIPT_DIR PHASES

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

validate_track_id() {
    local id="$1"
    case "${id}" in
        '' | .* | *..* | *[!A-Za-z0-9_.-]*)
            err "invalid track id: ${id:-<empty>}"
            return 64
            ;;
    esac
}

validate_state_path() {
    if ! python3 "${STATE_PATH_VALIDATOR}" "${XDG_STATE_ROOT}" "${STATE_DIR}"; then
        err "unsafe lifecycle state path: ${STATE_DIR}"
        return 64
    fi
}

track_path() {
    local id="$1" path
    validate_track_id "${id}" || return $?
    validate_state_path || return $?
    path="${STATE_DIR}/${id}.json"
    if [ -L "${path}" ]; then
        err "unsafe track path: ${path}"
        return 64
    fi
    printf '%s\n' "${path}"
}

ensure_state_dir() {
    validate_state_path || return $?
    if [ ! -d "${STATE_DIR}" ]; then
        mkdir -p "${STATE_DIR}"
        validate_state_path || return $?
        chmod 700 "${STATE_DIR}"
    fi
}

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
    p="$(track_path "$1")" || return $?
    tmp="$(mktemp "${STATE_DIR}/.track.XXXXXX")" || return $?
    printf '%s\n' "$2" > "${tmp}"
    chmod 600 "${tmp}"
    p="$(track_path "$1")" || {
        local rc=$?
        rm -f "${tmp}"
        return "${rc}"
    }
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

# Tracker and artifact phases are sourced from the same bundle.
# shellcheck disable=SC1091
source "$FORGE_RUNTIME_DIR/bin/lib/lifecycle_tracker.sh"
