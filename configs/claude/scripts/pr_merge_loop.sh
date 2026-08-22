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

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "pr-merge-loop: $*" >&2; else printf '%s\n' "pr-merge-loop: $*" >&2; fi; }

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
  tick <pr>                    Decide + dispatch one PR (lock, run-gate, act);
                                exit 12 = DEGRADED lease (lock unattemptable).
  run [--apply]                Self-paced bounded loop (10-min ceiling; stop at 5 empty).
  post-merge-check             main HEAD CI health (exit 10 on red).
USAGE
}

# --- platform I/O layer: split out of this file into pr_merge_loop_gh.sh
# (C-SIZE/CON-002 — see that file's header for the seam rationale). Provides
# gh_op, _owner_repo_from_remote, gh_threads_raw, count_unresolved_human.
# shellcheck source=pr_merge_loop_gh.sh disable=SC1091
source "${SCRIPT_DIR}/pr_merge_loop_gh.sh"

# --- pure classifier: raw gh values -> normalized signals JSON ---
CLASSIFY_PY='
import json, sys
buckets, rd, uh, disp, mrg, verify, hold, rev, maxrev, head = sys.argv[1:11]
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
  "max_revisions":int(maxrev or 3),"reviewer_error":False,"main_ci":"n/a",
  "head_sha":head or None}))
'

revisions_used() {
    local f="${STATE_DIR}/rev_${1}"
    [[ -f "$f" ]] && cat "$f" || echo 0
}

cmd_signals() {
    local pr="${1:?pr required}"
    local buckets rd uh disp mrg verify hold head
    buckets="$(gh_op checks "$pr" | tr '\n' ' ')"
    rd="$(gh_op reviewdecision "$pr")"
    uh="$(gh_op unresolved-human "$pr")"
    disp="$(gh_op disposition "$pr")"
    mrg="$(gh_op mergeable "$pr")"
    verify="$(gh_op verify "$pr")"
    hold="$(gh_op hold "$pr")"
    head="$(gh_op headsha "$pr")" # captured at decision time (finding 2 sink re-check)
    python3 -c "${CLASSIFY_PY}" "$buckets" "$rd" "$uh" "$disp" "$mrg" "$verify" "$hold" \
        "$(revisions_used "$pr")" "${MAX_REVISIONS:-3}" "$head"
}

# SECURITY (finding 1): `raw` is attacker-influenced — it is `gh pr list`'s author
# profile metadata, and a crafted display name (e.g. containing `'''` + Python) must
# never become part of the interpreted program text. LIST_MANAGED_PY is a CONSTANT,
# single-quoted string (no shell expansion happens inside it); `raw` is delivered
# exclusively via stdin and parsed with `json.load`, never interpolated into source.
LIST_MANAGED_PY='
import json, sys, yaml
try:
    prs = json.load(sys.stdin)
    if not isinstance(prs, list):
        raise ValueError("prs not a list")
except Exception:
    prs = []
try:
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception:
    cfg = {}
allow = {a.lower().replace("[bot]", "") for a in (cfg.get("authors") or [])}
out = []
for p in prs:
    a = (p.get("author") or {})
    login = (a.get("login") if isinstance(a, dict) else str(a)) or ""
    key = login.lower().replace("[bot]", "")
    is_bot = isinstance(a, dict) and (a.get("is_bot") or a.get("__typename") == "Bot")
    if key in allow or (cfg.get("trust_bot_typename") and is_bot):
        out.append({"number": p.get("number"), "author": login})
print(json.dumps(out))
'

cmd_list_managed() {
    local raw
    raw="$(gh_op list)"
    printf '%s' "$raw" | python3 -c "${LIST_MANAGED_PY}" "$AUTHORS_FILE"
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

# SECURITY (finding 5): $1, if given, pins the exact merge-commit sha to verify
# (set by cmd_tick right after a successful merge) so a concurrent merge landing
# on main in between can't make us grade someone else's commit. Falls back to
# reading main HEAD (pre-existing behaviour) when no sha is supplied.
cmd_post_merge_check() {
    local sha="${1:-}" state rc=0
    [[ -n "$sha" ]] || sha="$(git ls-remote origin main 2> /dev/null | awk 'NR==1{print $1}')"
    if [[ -z "$sha" ]]; then
        [[ -n "${PR_MERGE_LOOP_POSTMERGE_CMD:-}" ]] || {
            err "cannot read main sha — fail closed"
            return 10
        }
        sha="seam"
    fi
    if [[ -n "${PR_MERGE_LOOP_POSTMERGE_CMD:-}" ]]; then
        state="$("${PR_MERGE_LOOP_POSTMERGE_CMD}")" || rc=$?
    else
        # NOTE: github check-run conclusions (failure/cancelled/timed_out/action_required)
        # vs gitlab pipeline statuses (failed/canceled/...) use slightly different
        # vocabulary; the grep below matches github's. This path only runs on github
        # today (gitlab auto-merge fails closed before reaching post-merge-check).
        state="$(_net "${SCRIPT_DIR}/git_ops.sh" commit-checks "${sha}" 2> /dev/null)" || rc=$?
    fi
    # Explicit rc check (not `||`) — this function is invoked on the left of `||` by
    # callers, which suspends errexit for everything inside it; a failed status
    # command must never silently fall through to the `return 0` at the bottom.
    if [[ $rc -ne 0 ]]; then
        err "main CI status command failed (exit ${rc}) — fail closed, never success"
        return 10
    fi
    if [[ -z "${state//[[:space:]]/}" || "$state" == "[]" ]]; then
        err "main CI: no check results readable — fail closed, never success"
        return 10
    fi
    if printf '%s' "$state" | grep -qE 'failure|cancelled|timed_out|action_required'; then
        err "main CI red — HALT"
        return 10
    fi
    # A still-running check (null conclusion) or a "pending" status word is NOT
    # success either — only "neutral"/"skipped" completed conclusions pass through,
    # matching how gh's own check-run vocabulary distinguishes done-but-advisory
    # from not-yet-done.
    if printf '%s' "$state" | grep -qE 'null|pending'; then
        err "main CI still unresolved — HALT (never treat as success)"
        return 10
    fi
    return 0
}

# --- merge path (T019) + dispatch (T021) ---
APPLY="${PR_MERGE_LOOP_APPLY:-0}"
# SECURITY (finding-1 class, hardened preventively): the key is argv, never
# interpolated into the program text — only current callers pass literal keys
# ("action","label"), but the function itself must stay safe if that changes.
_JGET_PY='
import json, sys
v = json.load(sys.stdin).get(sys.argv[1])
print("" if v is None else v)
'
_jget() { python3 -c "${_JGET_PY}" "$1"; }

apply_label() { # apply_label <pr> <label> — no-op in dry-run; skips empty labels.
    [[ -n "${2:-}" && "$2" != "None" ]] || return 0
    [[ "$APPLY" == "1" ]] || {
        err "[dry-run] would label #$1 '$2'"
        return 0
    }
    "${SCRIPT_DIR}/git_ops.sh" issue-edit "$1" --add-label "$2" > /dev/null 2>&1 || err "could not label #$1 $2"
}

# SECURITY (finding 2): re-check a single login against the allowlist at the
# merge sink — deliberately independent of (and stricter than) cmd_list_managed's
# trust_bot_typename fallback, since the `author` op here only returns a login
# string, never a GraphQL __typename.
AUTHOR_ALLOWED_PY='
import json, sys, yaml
login = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    cfg = yaml.safe_load(open(sys.argv[2])) or {}
except Exception:
    cfg = {}
allow = {a.lower().replace("[bot]", "") for a in (cfg.get("authors") or [])}
key = (login or "").lower().replace("[bot]", "")
print("true" if key and key in allow else "false")
'
ALLOWED_BASE_BRANCH="${PR_MERGE_LOOP_ALLOWED_BASE:-main}"

# Re-derive every gate the loop normally enforces upstream, independently, right
# before the irreversible action — the public `merge` subcommand is directly
# callable and must never trust a decision computed (or not computed) elsewhere.
# Any lookup failure, empty value, or mismatch blocks (fail closed); no branch
# here ever grants an ambiguous "probably fine".
sink_reverify() {
    local pr="${1:?pr required}" expected_sha="${2:-}"
    local author allowed base head buckets hold uh

    author="$(gh_op author "$pr")" || {
        err "#$pr: author lookup failed — fail closed"
        return 1
    }
    [[ -n "$author" ]] || {
        err "#$pr: empty author — fail closed"
        return 1
    }
    allowed="$(python3 -c "${AUTHOR_ALLOWED_PY}" "$author" "$AUTHORS_FILE" 2> /dev/null)" || allowed=""
    [[ "$allowed" == "true" ]] || {
        err "#$pr: author '$author' not in the automation allowlist — fail closed"
        return 1
    }

    base="$(gh_op basebranch "$pr")" || {
        err "#$pr: base-branch lookup failed — fail closed"
        return 1
    }
    [[ "$base" == "$ALLOWED_BASE_BRANCH" ]] || {
        err "#$pr: base branch '$base' != '$ALLOWED_BASE_BRANCH' — fail closed"
        return 1
    }

    head="$(gh_op headsha "$pr")" || {
        err "#$pr: head-sha lookup failed — fail closed"
        return 1
    }
    [[ -n "$head" ]] || {
        err "#$pr: empty head sha — fail closed"
        return 1
    }
    if [[ -n "$expected_sha" && "$head" != "$expected_sha" ]]; then
        err "#$pr: head sha changed since decision ($expected_sha -> $head) — fail closed"
        return 1
    fi

    buckets="$(gh_op checks "$pr" | tr '\n' ' ')" || {
        err "#$pr: checks lookup failed — fail closed"
        return 1
    }
    if [[ -z "${buckets//[[:space:]]/}" ]] || printf '%s' "$buckets" | grep -qwE 'fail|cancel|pending'; then
        err "#$pr: checks not green ('${buckets}') — fail closed"
        return 1
    fi

    hold="$(gh_op hold "$pr")" || {
        err "#$pr: hold-label lookup failed — fail closed"
        return 1
    }
    [[ "$hold" == "false" ]] || {
        err "#$pr: hold label present — fail closed"
        return 1
    }

    uh="$(gh_op unresolved-human "$pr")" || {
        err "#$pr: unresolved-review lookup failed — fail closed"
        return 1
    }
    [[ "$uh" =~ ^[0-9]+$ && "$uh" -eq 0 ]] || {
        err "#$pr: unresolved human review threads (${uh}) — fail closed"
        return 1
    }
    return 0
}

LAST_MERGE_SHA="" # set by cmd_merge on a real do-merge success; read by cmd_tick.
cmd_merge() {
    local pr="${1:?pr required}" expected_sha="${2:-}" is_admin prot
    LAST_MERGE_SHA=""
    is_admin="$(gh_op admin-check "$pr")"
    [[ "$is_admin" == "true" ]] || {
        err "#$pr: no admin permission — fail closed"
        return 9
    }
    prot="$(gh_op protection "$pr")"
    if [[ "$prot" == "PROTECTION_LOOKUP_FAILED" ]] || printf '%s' "$prot" | grep -qE 'enforce_admins=true|required_signatures=true|merge_queue=true'; then
        err "#$pr: branch protection blocks admin bypass, or lookup failed ($prot) — fail closed"
        return 9
    fi
    if ! sink_reverify "$pr" "$expected_sha"; then
        err "#$pr: sink re-verification failed — fail closed"
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
    LAST_MERGE_SHA="$(gh_op mergecommit "$pr" 2> /dev/null || true)"
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
    local pr="${1:?pr required}" sig d act gate sig2 rc=0 head_sha lock_rc=0
    # HONESTY FIX (2026-08-20, CDDL developer-reviewer finding), superseded by
    # the PROPORTIONALITY FIX below: this copy's cmd_merge is a real `gh pr
    # merge --admin` (unlike the plugin bundle's vendored copy, which
    # hard-gates merge at exit 78), so a failed acquire here is NOT downgraded
    # to "proceed anyway" — see loop_lock.sh's header.
    #
    # PROPORTIONALITY FIX (2026-08-20, Finding 1): loop_lock.sh's `acquire` now
    # (a) self-provisions the dynamic `loop-active:<epoch>:<owner>` lease label
    # via `gh label create --force` before attaching it (labels.yml only ever
    # carried the static `loop-active`, and cannot carry this one — the
    # epoch+owner suffix is unbounded and generated fresh per acquisition), and
    # (b) reports WHY a failed acquire failed via distinct exit codes: 1 =
    # genuinely CONTENDED (someone else holds a live lease, we lost a race, or
    # same-host flock contention) — that is legitimate, skipping is correct,
    # exit 0 is correct. 2 = DEGRADED (the lease could not even be attempted —
    # e.g. label creation itself failed) — that is NOT evidence of contention.
    # Unlike the vendored copy (whose merge is hard-gated, so proceeding
    # without the cross-host lock on DEGRADED is safe), this copy's cmd_merge
    # performs a REAL admin merge — proceeding blind here could let two
    # concurrently-running loops both merge the same PR. So DEGRADED must NOT
    # be collapsed into a benign "skip" (exit 0): that would make exit-code-
    # based monitoring read success while no signal collection, merge
    # decision, or verification gate ever ran (the defect this fix closes).
    # Report it as a loud, distinct, nonzero operational error instead.
    "${SCRIPT_DIR}/loop_lock.sh" acquire "$pr" 2> /dev/null || lock_rc=$?
    case "$lock_rc" in
        0) : ;; # acquired the lease normally
        1)
            err "#$pr: locked — skipping (lease genuinely held by another run)"
            printf 'skip\n'
            return 0
            ;;
        *)
            err "#$pr: lease could not be attempted — label backend rejected the" \
                "add (DEGRADED, exit=${lock_rc}), NOT evidence of contention." \
                "This copy performs a real admin merge, so it will not proceed" \
                "without the cross-host lock: no signals, decision, or" \
                "verification gate ran for this PR. Treat this as an" \
                "operational fault, not '0 PRs were ready.'"
            return 12
            ;;
    esac
    # shellcheck disable=SC2064
    trap "'${SCRIPT_DIR}/loop_lock.sh' release '$pr' >/dev/null 2>&1" RETURN

    sig="$(cmd_signals "$pr")"
    head_sha="$(printf '%s' "$sig" | _jget head_sha)" # pinned for the sink SHA re-check
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
                cmd_merge "$pr" "$head_sha" || rc=$?
                if [[ $rc -eq 9 ]]; then
                    apply_label "$pr" ready-to-merge
                elif [[ $rc -eq 0 ]]; then
                    cmd_post_merge_check "$LAST_MERGE_SHA" > /dev/null 2>&1 || {
                        err "#$pr merged → main RED/pending — HALT"
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
# Exit 0 = ceiling/5-empty (normal); exit 11 = halt (main red post-merge);
# exit 12 = a tick hit a DEGRADED lease (propagated via errexit — cmd_tick's
# own nonzero return aborts the `act="$(cmd_tick "$pr")"` assignment, so the
# loop does not silently continue as if nothing were ready).
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
            # Finding 1(b): propagate cmd_tick's own exit code explicitly — a
            # DEGRADED lease (exit 12) must reach the caller/monitoring as a
            # real failure, not get flattened to a hardcoded success.
            cmd_tick "$@"
            exit $?
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
