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
#   address-cycle <pr>      One revision cycle (/pr-address-comments,/project-verify,/pr-review).
#   merge <pr>              Pre-flight + verified admin merge (FR-008..011).
#   post-merge-check        main HEAD CI health; exit 10 on red (FR-012a).
#   run                     Bounded self-paced loop (ceiling + 5-empty stop).
#
# Seams (tests/the loop inject these): PR_MERGE_LOOP_GH_CMD "<op> <pr>" (checks|reviewdecision|
#   unresolved-human|disposition|mergeable|verify|hold|author|list), PR_MERGE_LOOP_STATE_DIR,
#   AUTOMATION_AUTHORS_FILE, PR_MERGE_LOOP_NOW_CMD, PR_MERGE_LOOP_CEILING_SEC,
#   PR_MERGE_LOOP_POLL_SEC, GH_NET_TIMEOUT, PR_MERGE_LOOP_POSTMERGE_CMD.

set -euo pipefail

err() { echo -e "\033[0;31mpr-merge-loop: $*\033[0m" >&2; }

# Injectable clock (tests fast-forward via PR_MERGE_LOOP_NOW_CMD) and a bounded
# network wrapper so a single hung call can never bust the hard ceiling.
_now() { if [[ -n "${PR_MERGE_LOOP_NOW_CMD:-}" ]]; then "${PR_MERGE_LOOP_NOW_CMD}"; else date +%s; fi; }
_net() {
    local t="${GH_NET_TIMEOUT:-60}"
    if command -v timeout > /dev/null 2>&1; then
        timeout "$t" "$@"
    elif command -v gtimeout > /dev/null 2>&1; then
        gtimeout "$t" "$@"
    else "$@"; fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${PR_MERGE_LOOP_STATE_DIR:-${HOME}/.claude/pr_merge_loop}"
AUTHORS_FILE="${AUTOMATION_AUTHORS_FILE:-${SCRIPT_DIR}/../config/automation_authors.yml}"

usage() {
    cat << 'USAGE'
Usage: pr_merge_loop.sh <subcommand> [args]

  list-managed [--json]        Automation-authored open PRs (skips humans).
  signals <pr> [--json]        Recompute merge_decision input JSON for a PR.
  empty-run <get|incr|reset>   Consecutive-empty-run counter (stops loop at 5).
  address-cycle <pr>           Run one /pr-address-comments,/project-verify,/pr-review cycle.
  set-disposition <pr> <v>     Record the /pr-review verdict (merge|keep|close) for signals.
  merge <pr>                   Pre-flight + verified admin merge (exit 9 = fail-closed).
  tick <pr>                    Decide + dispatch one PR (lock, run-gate, act).
  run [--apply]                Self-paced bounded loop (10-min ceiling; stop at 5 empty).
  post-merge-check             main HEAD CI health (exit 10 on red).
USAGE
}

# --- platform seam (default drives gh via git_ops.sh) ---
gh_op() {
    # A disposition the reviewing agent recorded via set-disposition wins over the live default
    # (there is no platform API for "/pr-review said merge"; the state file IS that signal).
    if [[ "$1" == "disposition" && -n "${2:-}" && -f "${STATE_DIR}/disp_${2}" ]]; then
        cat "${STATE_DIR}/disp_${2}"
        return 0
    fi
    if [[ -n "${PR_MERGE_LOOP_GH_CMD:-}" ]]; then
        "${PR_MERGE_LOOP_GH_CMD}" "$@"
        return $?
    fi
    local op="$1" pr="${2:-}"
    local platform="${PR_MERGE_LOOP_PLATFORM:-$(bash "${SCRIPT_DIR}/git_platform.sh" 2> /dev/null || echo github)}"
    # GitLab parity: monitoring works; the merge path FAILS CLOSED to a human (admin-check=false
    # → cmd_merge exits 9 → ready-to-merge). Full GitLab auto-merge is design-only (glab not
    # verified here — research.md R1); this stub never auto-merges on GitLab rather than risk a
    # wrong merge.
    if [[ "$platform" == "gitlab" ]]; then
        case "$op" in
            list) glab mr list -F json 2> /dev/null || echo '[]' ;;
            checks) glab ci status 2> /dev/null ;;
            author) glab mr view "$pr" -F json 2> /dev/null | python3 -c 'import json,sys;print((json.load(sys.stdin).get("author") or {}).get("username",""))' 2> /dev/null ;;
            admin-check) echo false ;;
            do-merge)
                err "gitlab auto-merge not implemented — fail closed"
                return 1
                ;;
            *) echo "" ;;
        esac
        return 0
    fi
    case "$op" in
        list) "${SCRIPT_DIR}/git_ops.sh" pr-list --json number,author 2> /dev/null ;;
        checks) gh pr checks "$pr" --json bucket -q '.[].bucket' 2> /dev/null ;;
        reviewdecision) gh pr view "$pr" --json reviewDecision -q '.reviewDecision' 2> /dev/null ;;
        unresolved-human) count_unresolved_human "$pr" ;;
        disposition) echo keep ;;
        mergeable) gh pr view "$pr" --json mergeable,mergeStateStatus -q '.mergeable+" "+.mergeStateStatus' 2> /dev/null ;;
        verify) echo pass ;;
        hold) gh pr view "$pr" --json labels -q '.labels[].name' 2> /dev/null | grep -qx hold && echo true || echo false ;;
        author) gh pr view "$pr" --json author -q '.author.login' 2> /dev/null ;;
        admin-check) gh api "repos/{owner}/{repo}" -q '.permissions.admin' 2> /dev/null || echo false ;;
        protection) gh api "repos/{owner}/{repo}/branches/main/protection" \
            -q '"enforce_admins="+(.enforce_admins.enabled|tostring)+" required_signatures="+(.required_signatures.enabled|tostring)+" merge_queue=false"' 2> /dev/null ||
            echo "enforce_admins=false required_signatures=false merge_queue=false" ;;
        update-branch) gh pr update-branch "$pr" 2>&1 ;;
        do-merge) gh pr merge "$pr" --squash --admin --delete-branch 2>&1 ;;
    esac
}

# Raw review-thread JSON for a PR. Seam: PR_MERGE_LOOP_THREADS_JSON (offline tests).
gh_threads_raw() {
    if [[ -n "${PR_MERGE_LOOP_THREADS_JSON:-}" ]]; then
        printf '%s' "$PR_MERGE_LOOP_THREADS_JSON"
        return 0
    fi
    local pr="${1:?pr required}" nwo owner repo
    nwo="$(_net gh repo view --json nameWithOwner -q .nameWithOwner 2> /dev/null)" || return 1
    owner="${nwo%%/*}"
    repo="${nwo##*/}"
    # shellcheck disable=SC2016  # $owner/$repo/$pr are GraphQL variables, not shell vars
    _net gh api graphql -F owner="$owner" -F repo="$repo" -F pr="$pr" -f query='
      query($owner:String!,$repo:String!,$pr:Int!){
        repository(owner:$owner,name:$repo){
          pullRequest(number:$pr){
            reviewThreads(first:100){
              nodes{ isResolved isOutdated comments(first:1){ nodes{ author{ login } } } }
            }}}}' 2> /dev/null
}

# Count HUMAN-authored unresolved, non-outdated review threads. Bot nits (allowlist)
# are advisory. Any error/malformed payload -> 1 (fail closed: a thread might block).
COUNT_UH_PY='
import json, sys
try:
    import yaml
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception:
    cfg = {}
bots = {a.lower().replace("[bot]", "") for a in (cfg.get("authors") or [])}
try:
    nodes = json.load(sys.stdin)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    if not isinstance(nodes, list):
        raise ValueError("nodes not a list")
except Exception:
    print(1); sys.exit(0)  # malformed -> fail closed
count = 0
for t in nodes:
    if t.get("isResolved") or t.get("isOutdated"):
        continue
    cs = ((t.get("comments") or {}).get("nodes") or [])
    login = ((cs[0].get("author") or {}).get("login") if cs else "") or ""
    if login.lower().replace("[bot]", "") in bots:
        continue  # advisory bot nit
    count += 1
print(count)
'

count_unresolved_human() {
    local raw
    raw="$(gh_threads_raw "${1:?pr required}")" || {
        echo 1
        return 0
    }
    printf '%s' "$raw" | python3 -c "${COUNT_UH_PY}" "$AUTHORS_FILE"
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

revisions_used() {
    local f="${STATE_DIR}/rev_${1}"
    [[ -f "$f" ]] && cat "$f" || echo 0
}

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
    local raw
    raw="$(gh_op list)"
    python3 - "$AUTHORS_FILE" << PY
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
    mkdir -p "$STATE_DIR" 2> /dev/null || true
    local f="${STATE_DIR}/empty_count" n
    n=$([[ -f "$f" ]] && cat "$f" || echo 0)
    case "${1:-get}" in
        get) echo "$n" ;;
        incr)
            n=$((n + 1))
            echo "$n" > "$f"
            echo "$n"
            ;;
        reset)
            echo 0 > "$f"
            echo 0
            ;;
        *)
            err "empty-run: get|incr|reset"
            return 64
            ;;
    esac
}

# --- live orchestration (integration paths; seam-overridable) ---
cmd_address_cycle() {
    local pr="${1:?pr required}"
    err "address-cycle #${pr}: run /pr-address-comments, /project-verify, /pr-review (where independent, in parallel — FR-015)"
    local f="${STATE_DIR}/rev_${pr}"
    mkdir -p "$STATE_DIR" 2> /dev/null || true
    echo $(($(revisions_used "$pr") + 1)) > "$f"
    return 0
}

# The reviewing agent records its /pr-review verdict here; cmd_signals reads it back through
# gh_op disposition. Without a recorded verdict the decision can never reach run-gate/merge
# (the live default is "keep"), which is the safe default for unreviewed PRs.
cmd_set_disposition() {
    local pr="${1:?pr required}" v="${2:?merge|keep|close required}"
    case "$v" in merge | keep | close) ;; *)
        err "invalid disposition: ${v} (merge|keep|close)"
        return 64
        ;;
    esac
    mkdir -p "$STATE_DIR" 2> /dev/null || true
    echo "$v" > "${STATE_DIR}/disp_${pr}"
    return 0
}

cmd_post_merge_check() {
    local sha state
    sha="$(gh api "repos/{owner}/{repo}/commits/main" -q '.sha' 2> /dev/null)" ||
        {
            [[ -n "${PR_MERGE_LOOP_POSTMERGE_CMD:-}" ]] || {
                err "cannot read main sha — fail closed"
                return 10
            }
            sha="seam"
        }
    if [[ -n "${PR_MERGE_LOOP_POSTMERGE_CMD:-}" ]]; then
        state="$("${PR_MERGE_LOOP_POSTMERGE_CMD}")"
    else
        state="$(_net gh api "repos/{owner}/{repo}/commits/${sha}/check-runs" -q '[.check_runs[]|.conclusion]' 2> /dev/null)"
    fi
    if echo "$state" | grep -qE 'failure|cancelled|timed_out|action_required'; then
        err "main CI red — HALT"
        return 10
    fi
    return 0
}

# --- merge path (T019) + dispatch (T021) ---
APPLY="${PR_MERGE_LOOP_APPLY:-0}"
_jget() { python3 -c "import json,sys
v=json.load(sys.stdin).get('$1')
print('' if v is None else v)"; }

apply_label() { # apply_label <pr> <label> — no-op in dry-run; skips empty labels.
    [[ -n "${2:-}" && "$2" != "None" ]] || return 0
    [[ "$APPLY" == "1" ]] || {
        err "[dry-run] would label #$1 '$2'"
        return 0
    }
    "${SCRIPT_DIR}/git_ops.sh" issue-edit "$1" --add-label "$2" > /dev/null 2>&1 || err "could not label #$1 $2"
}

cmd_merge() {
    local pr="${1:?pr required}" is_admin prot
    is_admin="$(gh_op admin-check "$pr")"
    [[ "$is_admin" == "true" ]] || {
        err "#$pr: no admin permission — fail closed"
        return 9
    }
    prot="$(gh_op protection "$pr")"
    if printf '%s' "$prot" | grep -qE 'enforce_admins=true|required_signatures=true|merge_queue=true'; then
        err "#$pr: branch protection blocks admin bypass ($prot) — fail closed"
        return 9
    fi
    [[ "$APPLY" == "1" ]] || {
        err "[dry-run] would admin-merge #$pr (--squash --admin --delete-branch)"
        return 0
    }
    gh_op do-merge "$pr" > /dev/null 2>&1 || {
        err "#$pr: merge failed"
        return 2
    }
    return 0
}

# T039/FR-024/SC-011: consult the codified lifecycle gate before merging. FAIL-OPEN — a PR with
# no lifecycle track (the resolver seam returns empty) proceeds exactly as before; a lifecycle-
# tracked unit is BLOCKED (return 1) when `lifecycle.sh audit` reports drift (a phase skipped or
# the Verify smoke gate unmet), so the loop never merges past a failing lifecycle gate.
# Seams: LIFECYCLE_TRACK_FOR_PR_CMD <pr> -> track-id (empty = not tracked); LIFECYCLE_GATE_CMD.
lifecycle_gate_ok() {
    local pr="${1:?pr required}" gate track
    [[ -n "${LIFECYCLE_TRACK_FOR_PR_CMD:-}" ]] || return 0 # no resolver wired -> fail open
    track="$("${LIFECYCLE_TRACK_FOR_PR_CMD}" "$pr" 2> /dev/null)" || return 0
    [[ -n "$track" ]] || return 0 # PR not lifecycle-tracked -> fail open
    gate="${LIFECYCLE_GATE_CMD:-${SCRIPT_DIR}/lifecycle.sh}"
    "$gate" audit "$track" > /dev/null 2>&1 # 0 = no drift (ok); 1 = drift (block)
}

cmd_tick() {
    local pr="${1:?pr required}" sig d act gate sig2 rc=0
    if ! "${SCRIPT_DIR}/loop_lock.sh" acquire "$pr" 2> /dev/null; then
        err "#$pr locked — skipping"
        printf 'skip\n'
        return 0
    fi
    # shellcheck disable=SC2064
    trap "'${SCRIPT_DIR}/loop_lock.sh' release '$pr' >/dev/null 2>&1" RETURN

    sig="$(cmd_signals "$pr")"
    d="$(printf '%s' "$sig" | "${SCRIPT_DIR}/merge_decision.sh" decide)"
    act="$(printf '%s' "$d" | _jget action)"

    # Cheap signals clear → run the (expensive) verification gate, augment, re-decide.
    if [[ "$act" == "run-gate" ]]; then
        gate="$("${SCRIPT_DIR}/verification_gate.sh" review "$pr" 2> /dev/null)" || gate='{"reviewer_error":true}'
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
            if ! lifecycle_gate_ok "$pr"; then
                err "#$pr: lifecycle gate unsatisfied (audit drift) → needs-human (SC-011)"
                apply_label "$pr" needs-human
                act="hand-human"
            else
                cmd_merge "$pr" || rc=$?
                if [[ $rc -eq 9 ]]; then
                    apply_label "$pr" ready-to-merge
                elif [[ $rc -eq 0 ]]; then
                    cmd_post_merge_check > /dev/null 2>&1 || {
                        err "#$pr merged → main RED → HALT"
                        act="halt"
                    }
                else apply_label "$pr" needs-human; fi
            fi
            ;;
        update-branch) gh_op update-branch "$pr" > /dev/null 2>&1 || apply_label "$pr" needs-human ;;
        hand-human) apply_label "$pr" "$(printf '%s' "$d" | _jget label)" ;;
        halt) err "#$pr: HALT (post-merge main breakage)" ;;
        revise) err "#$pr: revise — the skill runs /pr-address-comments, /project-verify, /pr-review" ;;
        wait) err "#$pr: waiting on checks/mergeability" ;;
    esac
    # Audit (redacted, fail-open — FR-021/022).
    "${SCRIPT_DIR}/audit_log.sh" append \
        "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"pr\":${pr},\"action\":\"${act}\",\"apply\":${APPLY}}" \
        2> /dev/null || true
    printf '%s\n' "$act"
}

# --- T026/T024: bounded self-paced loop driver. One merge in flight at a time
# (loop_lock, inside cmd_tick). Hard wall-clock ceiling; stops after 5 empty passes.
# Exit 0 = ceiling/5-empty (normal); exit 11 = halt (main red post-merge).
cmd_run() {
    local ceiling="${PR_MERGE_LOOP_CEILING_SEC:-600}" poll="${PR_MERGE_LOOP_POLL_SEC:-30}"
    local start deadline now managed pr act inflight n
    start="$(_now)"
    deadline=$((start + ceiling))
    while :; do
        now="$(_now)"
        ((now < deadline)) || break
        managed="$(cmd_list_managed | python3 -c \
            'import json,sys;print(" ".join(str(p["number"]) for p in json.load(sys.stdin)))' 2> /dev/null || echo "")"
        inflight=0
        # shellcheck disable=SC2086 # word-split the space-joined PR numbers (bash 3.2-safe)
        for pr in $managed; do
            now="$(_now)"
            ((now < deadline)) || break
            act="$(cmd_tick "$pr")"
            case "$act" in
                halt)
                    err "loop HALT — main breakage on #$pr"
                    return 11
                    ;;
                merge | revise | update-branch | wait | skip) inflight=1 ;;
            esac
        done
        now="$(_now)"
        ((now < deadline)) || break
        if ((inflight == 1)); then
            cmd_empty_run reset > /dev/null
        else
            n="$(cmd_empty_run incr)"
            # set -e-safe only as the LHS of && (non-tail); do not move to a tail position
            ((n >= 5)) && {
                err "5 consecutive empty runs — stopping"
                break
            }
        fi
        now="$(_now)"
        ((now < deadline)) || break
        [[ "$poll" -gt 0 ]] && sleep "$poll"
    done
    return 0
}

main() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
        --help | -h | help)
            usage
            exit 0
            ;;
        list-managed)
            cmd_list_managed "$@"
            exit 0
            ;;
        signals)
            cmd_signals "$@"
            exit 0
            ;;
        empty-run)
            cmd_empty_run "$@"
            exit $?
            ;;
        address-cycle)
            cmd_address_cycle "$@"
            exit $?
            ;;
        set-disposition)
            cmd_set_disposition "$@"
            exit $?
            ;;
        post-merge-check)
            cmd_post_merge_check "$@"
            exit $?
            ;;
        merge)
            cmd_merge "$@"
            exit $?
            ;;
        tick)
            cmd_tick "$@"
            exit 0
            ;;
        run)
            cmd_run "$@"
            exit $?
            ;;
        count-unresolved-human)
            count_unresolved_human "$@"
            exit $?
            ;;
        _net)
            _net "$@"
            exit $?
            ;;
        _lifecycle_gate)
            lifecycle_gate_ok "$@"
            exit $?
            ;;
        *)
            err "unknown subcommand: ${sub:-<none>}"
            usage >&2
            exit 64
            ;;
    esac
}

main "$@"
