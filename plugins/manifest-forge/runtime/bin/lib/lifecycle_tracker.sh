# shellcheck shell=bash

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

TRACKER_REGISTRY="${FORGE_RUNTIME_DIR}/python/tracker_registry.py"

provider_registry_json() {
    python3 "${TRACKER_REGISTRY}" dump-registry
}

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
    local provider="$1" tier="$2" registry
    registry="$(provider_registry_json)" || {
        echo "ERR:unreadable-config"
        return 0
    }
    python3 -c '
import json, sys
try:
    cfg = json.loads(sys.argv[1]) or {}
except Exception:
    print("ERR:unreadable-config"); sys.exit(0)
p = (cfg.get("providers") or {}).get(sys.argv[2])
if not p:
    print("ERR:unknown-provider"); sys.exit(0)
c = (p.get("tier_map") or {}).get(int(sys.argv[3]))
print(str(c) if c is not None else "MISSING:%s" % p.get("missing_tier_behavior", "error"))
' "${registry}" "${provider}" "${tier}"
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
            err "provider config error: ${construct#ERR:} (tracker registry)"
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
    local provider="${1:-}" canonical="${2:-}" registry
    [ -n "${provider}" ] && [ -n "${canonical}" ] || {
        err "status-map requires <provider> <canonical-status>"
        return 64
    }
    registry="$(provider_registry_json)" || {
        err "cannot load tracker registry"
        return 2
    }
    python3 -c '
import json, sys
try:
    cfg = json.loads(sys.argv[1]) or {}
except Exception: sys.exit(2)
p = (cfg.get("providers") or {}).get(sys.argv[2])
if not p: sys.exit(2)
val = (p.get("status_map") or {}).get(sys.argv[3])
if val is None: sys.exit(2)
print("%s\t%s" % (p.get("status_via", "label"), val))
' "${registry}" "${provider}" "${canonical}" ||
        {
            err "status-map: no mapping for ${provider}/${canonical}"
            return 2
        }
}

# --- US5: review-gate verdict, loop-safe reconciliation, drift audit (FR-021,FR-026,FR-027) ---

phase_canonical() {
    local registry
    registry="$(provider_registry_json)" || {
        echo "in-progress"
        return 0
    }
    python3 -c '
import json, sys
try:
    m=(json.loads(sys.argv[1]) or {}).get("phase_to_canonical_status") or {}
    print(m.get(sys.argv[2],"in-progress"))
except Exception:
    print("in-progress")
' "${registry}" "$1"
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
