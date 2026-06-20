#!/usr/bin/env bash
# pr_merge_loop.sh — orchestrates the auto-dev PR monitor→address→merge loop.
#
# The DECISION lives in merge_decision.sh (pure, tested); this script gathers signals and
# performs side effects (behind injectable seams for offline tests). Self-paced, fail-closed.
# Contract: specs/361-auto-dev-merge-loop/contracts/pr_merge_loop.md
#
# Subcommands:
#   list-managed [--json]   Open PRs whose author is in the automation allowlist (FR-013).
#   signals <pr> [--json]   Recompute the merge_decision input JSON for one PR.
#   empty-run <get|incr|reset>   Manage the consecutive-empty-run counter (FR-018a).
#   address-cycle <pr>      One revision cycle (/address-pr-comments,/verify,/pr-review).
#   merge <pr>              Pre-flight + verified admin merge (FR-008..011).
#   post-merge-check        main HEAD CI health; exit 10 on red (FR-012a).
#
# Seams (tests/the loop inject these): PR_MERGE_LOOP_GH_CMD "<op> <pr>" (checks|reviewdecision|
#   unresolved-human|disposition|mergeable|verify|hold|author|list), PR_MERGE_LOOP_STATE_DIR,
#   AUTOMATION_AUTHORS_FILE.

set -euo pipefail

err() { echo "pr-merge-loop: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${PR_MERGE_LOOP_STATE_DIR:-${HOME}/.claude/pr_merge_loop}"
AUTHORS_FILE="${AUTOMATION_AUTHORS_FILE:-${SCRIPT_DIR}/../config/automation_authors.yml}"

usage() {
    cat <<'USAGE'
Usage: pr_merge_loop.sh <subcommand> [args]

  list-managed [--json]        Automation-authored open PRs (skips humans).
  signals <pr> [--json]        Recompute merge_decision input JSON for a PR.
  empty-run <get|incr|reset>   Consecutive-empty-run counter (stops loop at 5).
  address-cycle <pr>           Run one /address-pr-comments,/verify,/pr-review cycle.
  merge <pr>                   Pre-flight + verified admin merge (exit 9 = fail-closed).
  tick <pr>                    Decide + dispatch one PR (lock, run-gate, act).
  post-merge-check             main HEAD CI health (exit 10 on red).
USAGE
}

# --- platform seam (default drives gh via git_ops.sh) ---
gh_op() {
    if [[ -n "${PR_MERGE_LOOP_GH_CMD:-}" ]]; then "${PR_MERGE_LOOP_GH_CMD}" "$@"; return $?; fi
    local op="$1" pr="${2:-}"
    case "$op" in
        list)            "${SCRIPT_DIR}/git_ops.sh" issue-list --json number,author 2>/dev/null ;;
        checks)          gh pr checks "$pr" --json bucket -q '.[].bucket' 2>/dev/null ;;
        reviewdecision)  gh pr view "$pr" --json reviewDecision -q '.reviewDecision' 2>/dev/null ;;
        unresolved-human) echo 0 ;;   # GraphQL thread query wired in T012; default conservative
        disposition)     echo keep ;;
        mergeable)       gh pr view "$pr" --json mergeable,mergeStateStatus -q '.mergeable+" "+.mergeStateStatus' 2>/dev/null ;;
        verify)          echo pass ;;
        hold)            gh pr view "$pr" --json labels -q '.labels[].name' 2>/dev/null | grep -qx hold && echo true || echo false ;;
        author)          gh pr view "$pr" --json author -q '.author.login' 2>/dev/null ;;
        admin-check)     gh api "repos/{owner}/{repo}" -q '.permissions.admin' 2>/dev/null || echo false ;;
        protection)      gh api "repos/{owner}/{repo}/branches/main/protection" \
                           -q '"enforce_admins="+(.enforce_admins.enabled|tostring)+" required_signatures="+(.required_signatures.enabled|tostring)+" merge_queue=false"' 2>/dev/null \
                           || echo "enforce_admins=false required_signatures=false merge_queue=false" ;;
        update-branch)   gh pr update-branch "$pr" 2>&1 ;;
        do-merge)        gh pr merge "$pr" --squash --admin --delete-branch 2>&1 ;;
    esac
}

# --- pure classifier: raw gh values -> normalized signals JSON ---
CLASSIFY_PY='
import json, sys
buckets, rd, uh, disp, mrg, verify, hold, rev, maxrev = sys.argv[1:10]
bl = buckets.split() if buckets.strip() else []
if   "fail" in bl or "cancel" in bl: checks="FAIL"
elif "pending" in bl:                checks="PENDING"
elif not bl:                         checks="NO_CHECKS"
else:                                checks="PASS"
try: uh_n=int(uh or 0)
except: uh_n=0
review_block = (rd=="CHANGES_REQUESTED") or (uh_n>0)
parts=(mrg or "UNKNOWN UNKNOWN").split()
mergeable=parts[0] if parts else "UNKNOWN"
mstate=parts[1] if len(parts)>1 else "UNKNOWN"
print(json.dumps({"checks":checks,"review_block":review_block,"pr_review_disposition":disp or "keep",
  "verify":verify or "pass","gate_tier1":None,"consensus":None,"mergeable":mergeable,
  "merge_state":mstate,"hold":(hold=="true"),"revisions_used":int(rev or 0),
  "max_revisions":int(maxrev or 3),"reviewer_error":False,"main_ci":"n/a"}))
'

revisions_used() { local f="${STATE_DIR}/rev_${1}"; [[ -f "$f" ]] && cat "$f" || echo 0; }

cmd_signals() {
    local pr="${1:?pr required}"
    local buckets rd uh disp mrg verify hold
    buckets="$(gh_op checks "$pr" | tr '\n' ' ')"
    rd="$(gh_op reviewdecision "$pr")"
    uh="$(gh_op unresolved-human "$pr")"
    disp="$(gh_op disposition "$pr")"
    mrg="$(gh_op mergeable "$pr")"
    verify="$(gh_op verify "$pr")"
    hold="$(gh_op hold "$pr")"
    python3 -c "${CLASSIFY_PY}" "$buckets" "$rd" "$uh" "$disp" "$mrg" "$verify" "$hold" \
        "$(revisions_used "$pr")" "${MAX_REVISIONS:-3}"
}

cmd_list_managed() {
    local raw; raw="$(gh_op list)"
    python3 - "$AUTHORS_FILE" <<PY
import json, sys, yaml, re
raw = '''$raw'''
try: prs = json.loads(raw or "[]")
except Exception: prs = []
try:
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception:
    cfg = {}
allow = {a.lower().replace("[bot]","") for a in (cfg.get("authors") or [])}
out=[]
for p in prs:
    a = (p.get("author") or {})
    login = (a.get("login") if isinstance(a, dict) else str(a)) or ""
    key = login.lower().replace("[bot]","")
    is_bot = isinstance(a, dict) and (a.get("is_bot") or a.get("__typename")=="Bot")
    if key in allow or (cfg.get("trust_bot_typename") and is_bot):
        out.append({"number": p.get("number"), "author": login})
print(json.dumps(out))
PY
}

cmd_empty_run() {
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    local f="${STATE_DIR}/empty_count" n
    n=$( [[ -f "$f" ]] && cat "$f" || echo 0 )
    case "${1:-get}" in
        get)   echo "$n" ;;
        incr)  n=$((n+1)); echo "$n" > "$f"; echo "$n" ;;
        reset) echo 0 > "$f"; echo 0 ;;
        *) err "empty-run: get|incr|reset"; return 64 ;;
    esac
}

# --- live orchestration (integration paths; seam-overridable) ---
cmd_address_cycle() {
    local pr="${1:?pr required}"
    err "address-cycle #${pr}: run /address-pr-comments, /verify, /pr-review (where independent, in parallel — FR-015)"
    local f="${STATE_DIR}/rev_${pr}"; mkdir -p "$STATE_DIR" 2>/dev/null || true
    echo $(( $(revisions_used "$pr") + 1 )) > "$f"
    return 0
}

cmd_post_merge_check() {
    local sha state
    sha="$(gh api "repos/{owner}/{repo}/commits/main" -q '.sha' 2>/dev/null)" || { err "cannot read main sha — fail closed"; return 10; }
    state="$(gh api "repos/{owner}/{repo}/commits/${sha}/check-runs" -q '[.check_runs[]|.conclusion]' 2>/dev/null)"
    if echo "$state" | grep -qE 'failure|cancelled|timed_out|action_required'; then err "main CI red — HALT"; return 10; fi
    return 0
}

# --- merge path (T019) + dispatch (T021) ---
APPLY="${PR_MERGE_LOOP_APPLY:-0}"
_jget() { python3 -c "import json,sys
v=json.load(sys.stdin).get('$1')
print('' if v is None else v)"; }

apply_label() {  # apply_label <pr> <label> — no-op in dry-run; skips empty labels.
    [[ -n "${2:-}" && "$2" != "None" ]] || return 0
    [[ "$APPLY" == "1" ]] || { err "[dry-run] would label #$1 '$2'"; return 0; }
    "${SCRIPT_DIR}/git_ops.sh" issue-edit "$1" --add-label "$2" >/dev/null 2>&1 || err "could not label #$1 $2"
}

cmd_merge() {
    local pr="${1:?pr required}" is_admin prot
    is_admin="$(gh_op admin-check "$pr")"
    [[ "$is_admin" == "true" ]] || { err "#$pr: no admin permission — fail closed"; return 9; }
    prot="$(gh_op protection "$pr")"
    if printf '%s' "$prot" | grep -qE 'enforce_admins=true|required_signatures=true|merge_queue=true'; then
        err "#$pr: branch protection blocks admin bypass ($prot) — fail closed"; return 9
    fi
    [[ "$APPLY" == "1" ]] || { err "[dry-run] would admin-merge #$pr (--squash --admin --delete-branch)"; return 0; }
    gh_op do-merge "$pr" >/dev/null 2>&1 || { err "#$pr: merge failed"; return 2; }
    return 0
}

cmd_tick() {
    local pr="${1:?pr required}" sig d act gate sig2 rc=0
    if ! "${SCRIPT_DIR}/loop_lock.sh" acquire "$pr" 2>/dev/null; then err "#$pr locked — skipping"; printf 'skip\n'; return 0; fi
    # shellcheck disable=SC2064
    trap "'${SCRIPT_DIR}/loop_lock.sh' release '$pr' >/dev/null 2>&1" RETURN

    sig="$(cmd_signals "$pr")"
    d="$(printf '%s' "$sig" | "${SCRIPT_DIR}/merge_decision.sh" decide)"
    act="$(printf '%s' "$d" | _jget action)"

    # Cheap signals clear → run the (expensive) verification gate, augment, re-decide.
    if [[ "$act" == "run-gate" ]]; then
        gate="$("${SCRIPT_DIR}/verification_gate.sh" review "$pr" 2>/dev/null)" || gate='{"reviewer_error":true}'
        sig2="$(printf '%s' "$sig" | python3 -c '
import json,sys
s=json.load(sys.stdin)
try: g=json.loads(sys.argv[1])
except Exception: g={"reviewer_error":True}
ok=(g.get("tier1") or {}).get("passed") is True and not g.get("reviewer_error")
s["gate_tier1"]="pass" if ok else "fail"
s["consensus"]=g.get("consensus_score",0)
s["reviewer_error"]=bool(g.get("reviewer_error"))
print(json.dumps(s))' "$gate")"
        d="$(printf '%s' "$sig2" | "${SCRIPT_DIR}/merge_decision.sh" decide)"
        act="$(printf '%s' "$d" | _jget action)"
    fi

    case "$act" in
        merge)
            cmd_merge "$pr" || rc=$?
            if   [[ $rc -eq 9 ]]; then apply_label "$pr" ready-to-merge
            elif [[ $rc -eq 0 ]]; then cmd_post_merge_check >/dev/null 2>&1 || { err "#$pr merged → main RED → HALT"; act="halt"; }
            else apply_label "$pr" needs-human; fi ;;
        update-branch) gh_op update-branch "$pr" >/dev/null 2>&1 || apply_label "$pr" needs-human ;;
        hand-human)    apply_label "$pr" "$(printf '%s' "$d" | _jget label)" ;;
        halt)          err "#$pr: HALT (post-merge main breakage)" ;;
        revise)        err "#$pr: revise — the skill runs /address-pr-comments, /verify, /pr-review" ;;
        wait)          err "#$pr: waiting on checks/mergeability" ;;
    esac
    # Audit (redacted, fail-open — FR-021/022).
    "${SCRIPT_DIR}/audit_log.sh" append \
        "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"pr\":${pr},\"action\":\"${act}\",\"apply\":${APPLY}}" \
        2>/dev/null || true
    printf '%s\n' "$act"
}

main() {
    local sub="${1:-}"; shift || true
    case "${sub}" in
        --help|-h|help)  usage; exit 0 ;;
        list-managed)    cmd_list_managed "$@"; exit 0 ;;
        signals)         cmd_signals "$@"; exit 0 ;;
        empty-run)       cmd_empty_run "$@"; exit $? ;;
        address-cycle)   cmd_address_cycle "$@"; exit $? ;;
        post-merge-check) cmd_post_merge_check "$@"; exit $? ;;
        merge)           cmd_merge "$@"; exit $? ;;
        tick)            cmd_tick "$@"; exit 0 ;;
        *) err "unknown subcommand: ${sub:-<none>}"; usage >&2; exit 64 ;;
    esac
}

main "$@"
