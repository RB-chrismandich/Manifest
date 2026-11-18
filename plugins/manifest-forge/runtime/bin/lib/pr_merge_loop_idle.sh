# shellcheck shell=bash
# Human-idle preflight and explicit disposition recording. Uses the existing
# fingerprint state format; observation failure never certifies idle.
# fingerprint_recorded_action <pr> <material> — print the action persisted
# alongside a still-matching fingerprint (empty when no valid state exists).
# cmd_run uses it to distinguish "unchanged because settled" (hand-human, a
# hard-gated merge) from "unchanged but in flight" (wait/revise/update-branch);
# only the former may advance the consecutive-empty counter.
fingerprint_recorded_action() {
    local pr="${1:?pr required}" material="${2:?material required}" path
    fingerprint_state_matches "$pr" "$material" || return 0
    path="$(fingerprint_state_path "$pr" "$material")" || return 0
    python3 - "$path" << 'PY' 2> /dev/null || true
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["action"])
PY
}

cmd_address_status() {
    local pr="${1:?pr required}" material disposition=actionable fingerprint
    material="$(collect_fingerprint_material "$pr")" || return 13
    if [[ "$(fingerprint_recorded_action "$pr" "$material")" == "hand-human" ]]; then
        disposition=blocked
    fi
    if [[ "${2:-}" == "--json" ]]; then
        fingerprint="$(printf '%s' "$material" | _jget fingerprint)" || return 13
        printf '{"status":"%s","fingerprint":"%s"}\n' "$disposition" "$fingerprint"
    elif [[ "$disposition" == blocked ]]; then
        printf 'blocked on human: #%s\n' "$pr"
    else
        printf 'actionable: #%s\n' "$pr"
    fi
}

cmd_record_human_blocked() {
    local pr="${1:?pr required}" expected="${2:?observed fingerprint required}" material fingerprint
    material="$(collect_fingerprint_material "$pr")" || return 13
    fingerprint="$(printf '%s' "$material" | _jget fingerprint)" || return 13
    if [[ "$expected" != "$fingerprint" ]]; then
        err "#$pr: material changed — human disposition not recorded"
        return 13
    fi
    persist_fingerprint_state "$pr" "$material" hand-human || return 13
    printf 'blocked on human: #%s\n' "$pr"
}
human_idle_turn() {
    local managed="${1:?managed PRs required}" scope path
    scope="$(gh_op fp-scope)" || return 13
    path="$(printf '%s' "$scope" | python3 -c '
import hashlib,json,os,sys
s=json.load(sys.stdin)
h=hashlib.sha256((s["host"].lower().rstrip(".")+"\0"+s["owner_repo"]).encode()).hexdigest()
print(os.path.join(sys.argv[1],"human_idle_"+h+".json"))
' "$STATE_DIR")" || return 13
    python3 - "$path" "$STATE_DIR" "$(basename "$path" .json | sed 's/^human_idle_//')" "$managed" << 'PY'
import json,os,sys,tempfile
path,state_dir,scope_hash,raw=sys.argv[1:5]
prs=raw.split()
observed={}
for pr in prs:
    filename=os.path.join(state_dir,"fp_"+scope_hash+"_"+pr+".json")
    try:
        with open(filename,encoding="utf-8") as f: state=json.load(f)
        if (state.get("action")!="hand-human"
                or not isinstance(state.get("observed_at"),str) or not state["observed_at"]
                or not isinstance(state.get("fingerprint"),str) or not state["fingerprint"]):
            raise ValueError()
        observed[pr]={"observed_at":state["observed_at"],"fingerprint":state["fingerprint"]}
    except Exception:
        raise SystemExit(13)
try:
    with open(path,encoding="utf-8") as f: previous=json.load(f)
    count=previous["count"] if previous["observed"]==observed else 0
except Exception:
    count=0
count+=1
os.makedirs(state_dir,mode=0o700,exist_ok=True)
fd,tmp=tempfile.mkstemp(dir=state_dir)
try:
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump({"observed":observed,"count":count},f,sort_keys=True)
        f.write("\n")
    os.chmod(tmp,0o600); os.replace(tmp,path)
except Exception:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
    raise
print(count)
PY
}
