#!/usr/bin/env bash
# pr_merge_loop.sh — orchestrates the auto-dev PR monitor→address→merge loop.
#
# The DECISION lives in merge_decision.sh (pure, tested); this script gathers signals and
# performs side effects (behind injectable seams for offline tests). Self-paced, fail-closed.
# Contract: specs/361-auto-dev-merge-loop/contracts/pr_merge_loop.md
#
# HARD GATE (THIS VENDORED COPY ONLY — CDDL QA-critic finding, 2026-08-19/20): the
# `merge` action is unreachable. cmd_merge refuses unconditionally, first thing,
# before any other logic — see merge_capability_disabled() below for the full,
# current rationale (originally an inert concurrency lock and a false-green
# test, since fixed — 2026-08-20, Finding 1(a) — but the gate is independent
# of that fix; 6 further open findings on the loop's own safety invariants
# remain, unaffected).
# PR_MERGE_LOOP_APPLY=1 does NOT re-enable it here: the gate is not an env toggle.
# The operator's bootstrap-deployed copy of this same script (outside plugins/,
# the coordinator's own bootstrap-only home tree) is unaffected — this task
# deliberately does not touch it. Everything read-only
# (list-managed, signals, decide, address-cycle, tick-up-to-merge, post-merge-check)
# keeps working. See docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md
# §4 Phase 1 item 1.3.
#
# Subcommands:
#   list-managed [--json]   Open PRs whose author is in the automation allowlist (FR-013).
#   signals <pr> [--json]   Recompute the merge_decision input JSON for one PR.
#   empty-run <get|incr|reset>   Manage the consecutive-empty-run counter (FR-018a).
#   address-cycle <pr>      One revision cycle (/pr-address-comments,/project-verify,/pr-review).
#   merge <pr>              HARD-GATED in this bundle — always refuses (see above); exit 78.
#   post-merge-check        main HEAD CI health; exit 10 on red (FR-012a).
#   run                     Bounded self-paced loop (ceiling + 5-empty stop).
#
# Seams (tests/the loop inject these): PR_MERGE_LOOP_GH_CMD "<op> <pr>" (checks|reviewdecision|
#   unresolved-human|disposition|mergeable|hold|author|list), PR_MERGE_LOOP_STATE_DIR,
#   AUTOMATION_AUTHORS_FILE, PR_MERGE_LOOP_NOW_CMD, PR_MERGE_LOOP_CEILING_SEC,
#   PR_MERGE_LOOP_POLL_SEC, GH_NET_TIMEOUT, PR_MERGE_LOOP_POSTMERGE_CMD.

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "pr-merge-loop: $*" >&2; else printf '%s\n' "pr-merge-loop: $*" >&2; fi; }

# Injectable clock (tests fast-forward via PR_MERGE_LOOP_NOW_CMD) and a bounded
# network wrapper so a single hung call can never bust the hard ceiling.
_now() { if [[ -n "${PR_MERGE_LOOP_NOW_CMD:-}" ]]; then "${PR_MERGE_LOOP_NOW_CMD}"; else date +%s; fi; }
_observed_at() {
    if [[ -n "${PR_MERGE_LOOP_CLOCK_CMD:-}" ]]; then
        "${PR_MERGE_LOOP_CLOCK_CMD}"
    else
        date -u +%Y-%m-%dT%H:%M:%SZ
    fi
}
_net() {
    local t="${GH_NET_TIMEOUT:-60}"
    if command -v timeout > /dev/null 2>&1; then
        timeout "$t" "$@"
    elif command -v gtimeout > /dev/null 2>&1; then
        gtimeout "$t" "$@"
    else "$@"; fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# XDG state root, matching every other manifest-forge runtime script (FORGE_STATE_DIR
# convention in audit_log.sh, lifecycle.sh, etc.) — not the coordinator's
# bootstrap-only home tree, which this portable bundle does not depend on.
STATE_DIR="${PR_MERGE_LOOP_STATE_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/manifest/forge/pr_merge_loop}"
AUTHORS_FILE="${AUTOMATION_AUTHORS_FILE:-${SCRIPT_DIR}/../config/automation_authors.json}"

usage() {
    cat << 'USAGE'
Usage: pr_merge_loop.sh <subcommand> [args]

  list-managed [--json]        Automation-authored open PRs (skips humans).
  signals <pr> [--json]        Recompute merge_decision input JSON for a PR.
  empty-run <get|incr|reset>   Consecutive-empty-run counter (stops loop at 5).
  address-cycle <pr>           Run one /pr-address-comments,/project-verify,/pr-review cycle.
  set-disposition <pr> <v>     Record the /pr-review verdict (merge|keep|close) for signals.
  merge <pr>                   HARD-GATED in this bundle: always refuses, exit 78.
  tick <pr>                    Decide + dispatch one PR (lock, run-gate, act).
  run [--apply]                Self-paced bounded loop (10-min ceiling; stop at 5 empty).
  post-merge-check             main HEAD CI health (exit 10 on red).
USAGE
}

# --- platform I/O layer: split out of this file into lib/pr_merge_loop_gh.sh
# (C-SIZE/CON-002 — see that file's header for the seam rationale). Provides
# gh_op, _owner_repo_from_remote, gh_threads_raw, count_unresolved_human.
# shellcheck source=lib/pr_merge_loop_gh.sh disable=SC1091
source "${SCRIPT_DIR}/lib/pr_merge_loop_gh.sh"

# --- pure classifier: raw gh values -> normalized signals JSON ---
CLASSIFY_PY='
import json, sys
buckets, rd, uh, disp, mrg, main_ci, hold, rev, maxrev, head = sys.argv[1:11]
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
  "gate_tier1":None,"mergeable":mergeable,
  "merge_state":mstate,"hold":(hold=="true"),"revisions_used":int(rev or 0),
  "max_revisions":int(maxrev or 3),"reviewer_error":False,"main_ci":main_ci,
  "head_sha":head or None}))
'

revisions_used() {
    local f="${STATE_DIR}/rev_${1}"
    [[ -f "$f" ]] && cat "$f" || echo 0
}

cmd_signals() {
    local pr="${1:?pr required}"
    local buckets rd uh disp mrg hold head
    buckets="$(gh_op checks "$pr" | tr '\n' ' ')" || {
        err "#$pr: checks observation failed"
        return 13
    }
    rd="$(gh_op reviewdecision "$pr")" || {
        err "#$pr: review-decision observation failed"
        return 13
    }
    uh="$(gh_op unresolved-human "$pr")" || {
        err "#$pr: review-thread observation failed"
        return 13
    }
    disp="$(gh_op disposition "$pr")" || {
        err "#$pr: disposition observation failed"
        return 13
    }
    mrg="$(gh_op mergeable "$pr")" || {
        err "#$pr: mergeability observation failed"
        return 13
    }
    # main-ci health replaces the retired `verify` signal: with no sha arg
    # cmd_post_merge_check reads main HEAD and is fail-closed — unreadable or
    # pending main CI counts as red, which decide() maps to halt.
    local main_ci=green
    cmd_post_merge_check > /dev/null 2>&1 || main_ci=red
    hold="$(gh_op hold "$pr")" || {
        err "#$pr: hold observation failed"
        return 13
    }
    head="$(gh_op headsha "$pr")" || {
        err "#$pr: head-sha observation failed"
        return 13
    }
    [[ -n "$mrg" && "$hold" =~ ^(true|false)$ && -n "$head" ]] || {
        err "#$pr: signal observation was incomplete"
        return 13
    }
    python3 -c "${CLASSIFY_PY}" "$buckets" "$rd" "$uh" "$disp" "$mrg" "$main_ci" "$hold" \
        "$(revisions_used "$pr")" "${MAX_REVISIONS:-3}" "$head"
}

# SECURITY (finding 1): `raw` is attacker-influenced — it is `gh pr list`'s author
# profile metadata, and a crafted display name (e.g. containing `'''` + Python) must
# never become part of the interpreted program text. LIST_MANAGED_PY is a CONSTANT,
# single-quoted string (no shell expansion happens inside it); `raw` is delivered
# exclusively via stdin and parsed with `json.load`, never interpolated into source.
LIST_MANAGED_PY='
import json, sys
try:
    prs = json.load(sys.stdin)
    if not isinstance(prs, list):
        raise ValueError("prs not a list")
except Exception:
    prs = []
try:
    cfg = json.load(open(sys.argv[1])) or {}
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
    local sha="${1:-}" state rc=0 repo=""
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
        # GitHub check-run conclusions are queried only after deriving the
        # selected remote's owner/repository; failure is fail-closed.
        repo="$(_owner_repo_from_remote)" || {
            err "cannot resolve GitHub repository — fail closed"
            return 10
        }
        state="$(_net gh api "repos/${repo}/commits/${sha}/check-runs" -q '[.check_runs[]|.conclusion]' 2> /dev/null)" || rc=$?
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

# Canonicalize every material input in one place. Raw host responses live only
# in a private temporary directory and are deleted before this function returns.
# Output is sanitized digest metadata, never endpoint/check/review content.
FINGERPRINT_PY='
import hashlib
import json
import sys

scope_path, view_path, checks_path, threads_path = sys.argv[1:5]
apply_mode, revision, max_revision, disposition, main_ci, hold = sys.argv[5:11]

def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)

def require_text(value, field, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(field)
    return value

def optional_text(value, field):
    if value is None:
        return None
    return require_text(value, field, allow_empty=True)

scope = load_json(scope_path)
if not isinstance(scope, dict):
    raise ValueError("scope")
host = require_text(scope.get("host"), "scope.host").lower().rstrip(".")
owner_repo = require_text(scope.get("owner_repo"), "scope.owner_repo")
if owner_repo.count("/") != 1:
    raise ValueError("scope.owner_repo")

view = load_json(view_path)
required_view = {
    "headRefOid", "baseRefName", "mergeable", "mergeStateStatus",
    "reviewDecision", "latestReviews", "labels", "isDraft", "state",
}
if not isinstance(view, dict) or not required_view.issubset(view):
    raise ValueError("view")
if not isinstance(view["isDraft"], bool):
    raise ValueError("view.isDraft")

reviews = []
if not isinstance(view["latestReviews"], list):
    raise ValueError("view.latestReviews")
for review in view["latestReviews"]:
    if not isinstance(review, dict):
        raise ValueError("review")
    reviews.append({
        "id": require_text(review.get("id"), "review.id"),
        "state": require_text(review.get("state"), "review.state"),
        "submittedAt": require_text(review.get("submittedAt"), "review.submittedAt"),
    })
reviews.sort(key=lambda item: (item["id"], item["state"], item["submittedAt"]))

if not isinstance(view["labels"], list):
    raise ValueError("view.labels")
audit_labels = {"loop-active", "needs-human", "ready-to-merge", "processed"}
labels = []
for label in view["labels"]:
    if not isinstance(label, dict):
        raise ValueError("label")
    name = require_text(label.get("name"), "label.name")
    folded = name.casefold()
    if folded in audit_labels or folded.startswith("loop-active:"):
        continue
    labels.append(name)
labels.sort(key=lambda item: (item.casefold(), item))

checks_raw = load_json(checks_path)
if not isinstance(checks_raw, list):
    raise ValueError("checks")
checks = []
for check in checks_raw:
    if not isinstance(check, dict):
        raise ValueError("check")
    checks.append({
        "name": require_text(check.get("name"), "check.name"),
        "bucket": require_text(check.get("bucket"), "check.bucket"),
        "state": require_text(check.get("state"), "check.state"),
        "link": optional_text(check.get("link"), "check.link"),
        "startedAt": optional_text(check.get("startedAt"), "check.startedAt"),
        "completedAt": optional_text(check.get("completedAt"), "check.completedAt"),
    })
checks.sort(key=lambda item: tuple("" if item[key] is None else item[key] for key in
    ("name", "bucket", "state", "link", "startedAt", "completedAt")))

with open(threads_path, encoding="utf-8") as handle:
    pages = [json.loads(line) for line in handle if line.strip()]
if not pages:
    raise ValueError("threads")
threads = []
for page_index, page in enumerate(pages):
    try:
        connection = page["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes = connection["nodes"]
        page_info = connection["pageInfo"]
    except (KeyError, TypeError):
        raise ValueError("threads") from None
    if not isinstance(nodes, list) or not isinstance(page_info, dict):
        raise ValueError("threads")
    if page_index == len(pages) - 1 and page_info.get("hasNextPage") is not False:
        raise ValueError("threads.incomplete")
    for thread in nodes:
        if not isinstance(thread, dict):
            raise ValueError("thread")
        if not isinstance(thread.get("isResolved"), bool) or not isinstance(thread.get("isOutdated"), bool):
            raise ValueError("thread.state")
        latest = (thread.get("latestComments") or {}).get("nodes")
        if not isinstance(latest, list) or len(latest) > 1:
            raise ValueError("thread.latestComments")
        latest_comment = latest[0] if latest else {}
        if latest_comment and not isinstance(latest_comment, dict):
            raise ValueError("thread.latestComment")
        threads.append({
            "id": require_text(thread.get("id"), "thread.id"),
            "isResolved": thread["isResolved"],
            "isOutdated": thread["isOutdated"],
            "latestCommentId": optional_text(latest_comment.get("id"), "thread.latestComment.id"),
            "latestCommentCreatedAt": optional_text(
                latest_comment.get("createdAt"), "thread.latestComment.createdAt"
            ),
        })
threads.sort(key=lambda item: (
    item["id"], item["isResolved"], item["isOutdated"],
    item["latestCommentId"] or "", item["latestCommentCreatedAt"] or "",
))

if apply_mode not in {"0", "1"}:
    raise ValueError("apply")
try:
    revision_number = int(revision)
    max_revision_number = int(max_revision)
except ValueError:
    raise ValueError("revision") from None
if revision_number < 0 or max_revision_number < 1:
    raise ValueError("revision")
if disposition not in {"merge", "keep", "close"}:
    raise ValueError("disposition")
if hold not in {"true", "false"}:
    raise ValueError("hold")
if main_ci not in {"green", "red", "n/a"}:
    raise ValueError("main_ci")

external = {
    "repository": {"host": host, "owner_repo": owner_repo},
    "view": {
        "headRefOid": require_text(view["headRefOid"], "view.headRefOid"),
        "baseRefName": require_text(view["baseRefName"], "view.baseRefName"),
        "mergeable": require_text(view["mergeable"], "view.mergeable"),
        "mergeStateStatus": require_text(view["mergeStateStatus"], "view.mergeStateStatus"),
        "reviewDecision": optional_text(view["reviewDecision"], "view.reviewDecision"),
        "latestReviews": reviews,
        "labels": labels,
        "isDraft": view["isDraft"],
        "state": require_text(view["state"], "view.state"),
    },
    "checks": checks,
    "threads": threads,
    "hold": hold == "true",
    "main_ci": main_ci,
}
local = {
    "apply": apply_mode == "1",
    "revisions_used": revision_number,
    "max_revisions": max_revision_number,
    "disposition": disposition,
}

def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()

scope_hash = hashlib.sha256((host + "\0" + owner_repo).encode()).hexdigest()
print(json.dumps({
    "schema_version": 1,
    "scope_hash": scope_hash,
    "fingerprint": digest({"external": external, "local": local}),
    "external_fingerprint": digest(external),
}, sort_keys=True, separators=(",", ":")))
'

collect_fingerprint_material() {
    local pr="${1:?pr required}" tmp out disposition main_ci hold rc=0
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/manifest-pr-fp.XXXXXX")" || {
        err "#$pr: cannot create private observation workspace"
        return 13
    }
    chmod 700 "$tmp" 2> /dev/null || {
        rm -rf "$tmp"
        err "#$pr: cannot secure private observation workspace"
        return 13
    }
    gh_op fp-scope "$pr" > "$tmp/scope" || rc=$?
    [[ $rc -eq 0 ]] && gh_op fp-view "$pr" > "$tmp/view" || rc=$?
    [[ $rc -eq 0 ]] && gh_op fp-checks "$pr" > "$tmp/checks" || rc=$?
    [[ $rc -eq 0 ]] && gh_op fp-threads "$pr" > "$tmp/threads" || rc=$?
    if [[ $rc -ne 0 ]]; then
        rm -rf "$tmp"
        err "#$pr: complete material observation unavailable (exit ${rc})"
        return 13
    fi
    disposition="$(gh_op disposition "$pr")" || rc=$?
    main_ci=green
    cmd_post_merge_check > /dev/null 2>&1 || main_ci=red
    [[ $rc -eq 0 ]] && hold="$(gh_op hold "$pr")" || rc=$?
    if [[ $rc -ne 0 ]]; then
        rm -rf "$tmp"
        err "#$pr: actionable input observation unavailable (exit ${rc})"
        return 13
    fi
    out="$(python3 -c "${FINGERPRINT_PY}" \
        "$tmp/scope" "$tmp/view" "$tmp/checks" "$tmp/threads" \
        "$APPLY" "$(revisions_used "$pr")" "${MAX_REVISIONS:-3}" \
        "$disposition" "$main_ci" "$hold" 2> /dev/null)" || rc=$?
    rm -rf "$tmp"
    if [[ $rc -ne 0 || -z "$out" ]]; then
        err "#$pr: material observation was incomplete or unparseable"
        return 13
    fi
    printf '%s\n' "$out"
}

fingerprint_state_path() {
    local pr="${1:?pr required}" material="${2:?material required}" scope_hash
    scope_hash="$(printf '%s' "$material" | _jget scope_hash 2> /dev/null)" || return 1
    [[ "$pr" =~ ^[0-9]+$ && "$scope_hash" =~ ^[0-9a-f]{64}$ ]] || return 1
    printf '%s/fp_%s_%s.json\n' "$STATE_DIR" "$scope_hash" "$pr"
}

fingerprint_state_matches() {
    local pr="${1:?pr required}" material="${2:?material required}" path fingerprint
    path="$(fingerprint_state_path "$pr" "$material")" || return 1
    [[ -f "$path" ]] || return 1
    fingerprint="$(printf '%s' "$material" | _jget fingerprint 2> /dev/null)" || return 1
    python3 - "$path" "$fingerprint" <<'PY' 2> /dev/null
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
valid = (
    isinstance(state, dict)
    and set(state) == {"schema_version", "fingerprint", "action", "observed_at"}
    and state.get("schema_version") == 1
    and isinstance(state.get("fingerprint"), str)
    and isinstance(state.get("action"), str)
    and bool(state["action"])
    and isinstance(state.get("observed_at"), str)
    and bool(state["observed_at"])
)
sys.exit(0 if valid and state["fingerprint"] == sys.argv[2] else 1)
PY
}

persist_fingerprint_state() {
    local pr="${1:?pr required}" material="${2:?material required}" action="${3:?action required}"
    local path fingerprint observed
    path="$(fingerprint_state_path "$pr" "$material")" || return 1
    fingerprint="$(printf '%s' "$material" | _jget fingerprint 2> /dev/null)" || return 1
    observed="$(_observed_at)" || return 1
    python3 - "$path" "$fingerprint" "$action" "$observed" <<'PY'
import json
import os
import sys
import tempfile

path, fingerprint, action, observed = sys.argv[1:5]
parent = os.path.dirname(path)
os.makedirs(parent, mode=0o700, exist_ok=True)
os.chmod(parent, 0o700)
payload = {
    "schema_version": 1,
    "fingerprint": fingerprint,
    "action": action,
    "observed_at": observed,
}
descriptor, temporary = tempfile.mkstemp(
    dir=parent, prefix="." + os.path.basename(path) + ".tmp."
)
try:
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        descriptor = -1
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600)
except Exception:
    if descriptor >= 0:
        os.close(descriptor)
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}

fingerprint_external_matches() {
    local before="${1:?before material required}" after="${2:?after material required}"
    local before_scope after_scope before_external after_external
    before_scope="$(printf '%s' "$before" | _jget scope_hash 2> /dev/null)" || return 1
    after_scope="$(printf '%s' "$after" | _jget scope_hash 2> /dev/null)" || return 1
    before_external="$(printf '%s' "$before" | _jget external_fingerprint 2> /dev/null)" || return 1
    after_external="$(printf '%s' "$after" | _jget external_fingerprint 2> /dev/null)" || return 1
    [[ "$before_scope" == "$after_scope" && "$before_external" == "$after_external" ]]
}

# apply_label <pr> <label> — no-op in dry-run; skips empty labels.
apply_label() {
    [[ -n "${2:-}" && "$2" != "None" ]] || return 0
    [[ "$APPLY" == "1" ]] || {
        err "[dry-run] would label #$1 '$2'"
        return 0
    }
    gh_op add-label "$1" "$2" > /dev/null 2>&1 || {
        err "could not label #$1 $2"
        return 1
    }
}

# HARD GATE (this vendored copy only — CDDL QA-critic finding, 2026-08-19/20).
# The pre-flight/sink-reverify implementation that used to live in cmd_merge
# (admin-check, branch-protection check, sink_reverify's independent re-read of
# author/base/head-sha/checks/hold/unresolved-review) is INTENTIONALLY REMOVED
# from this copy, not merely bypassed — a guard sitting in front of live merge
# code is still one missed `return` away from executing it, and dead code after
# an unconditional return also fails `shellcheck` (SC2317). Deleting it is what
# makes the gate structural rather than a toggle.
#
# That logic is NOT lost: it is unchanged in the operator's bootstrap-deployed
# copy of this same script (out of scope for this task — see that file's
# `sink_reverify`) and in this file's git history, ready to restore verbatim
# once the safety spec below lands.
#
# Single chokepoint: cmd_merge is the only path to `gh pr merge`, so this call
# blocks the `merge` subcommand and cmd_tick's merge branch alike. Not an env
# toggle — PR_MERGE_LOOP_APPLY does not bypass it.
readonly MERGE_HARD_GATE_EXIT=78
merge_capability_disabled() {
    local pr="${1:?pr required}"
    err "#$pr: automated merge is disabled in this plugin bundle."
    # UPDATED (2026-08-20, Finding 1(a)): the concurrency-lock defect that
    # originally justified this gate (loop_lock.sh's dynamic lease label was
    # never provisioned, so the lock was known-inert) is now fixed —
    # label_op self-provisions it before attaching. Restating the old reason
    # here would be exactly the kind of stale, misleading error text this
    # codebase's own "HONESTY FIX" history exists to prevent: an operator
    # reading it would wrongly conclude fixing the lock unblocks merges. The
    # gate stays anyway — for the BROADER reasons the companion safety spec
    # was always about: no atomic re-read of all signals immediately before
    # merge (stale-signal TOCTOU), no idempotent retries, no post-merge
    # failure handling, and no crash/concurrency mutation tests. Fixing
    # reachability (vendoring, the lock) was never a claim of safety.
    err "reason: this loop lacks the safety invariants the companion spec" \
        "requires before an automated admin-squash-merge is trusted — an" \
        "atomic re-read of all signals immediately before merge, idempotent" \
        "retries, and crash/concurrency mutation tests, among others. See" \
        "docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md §4" \
        "Phase 1 item 1.3. (The concurrency-lock defect once cited here is" \
        "fixed — see loop_lock.sh's label_op — but this gate is independent" \
        "of that and does not lift because of it.)"
    err "read-only subset unaffected: list-managed/signals/decide/address-cycle/tick-to-gate."
    return "$MERGE_HARD_GATE_EXIT"
}

LAST_MERGE_SHA="" # never set in this copy (see gate above); kept so cmd_tick's
# rc==0 branch and post-merge-check's empty-sha fallback stay well-defined.
cmd_merge() {
    local pr="${1:?pr required}"
    merge_capability_disabled "$pr"
    return $?
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
    local pr="${1:?pr required}" sig d act gate sig2 head_sha
    local material post_material rc=0 lock_rc=0 handling_failed=0 lock_degraded=0

    # Observe before touching the mutation lease. An exact valid state match is
    # the cheap path: no lease label, reviewer, action label, or audit append.
    material="$(collect_fingerprint_material "$pr")" || return 13
    if fingerprint_state_matches "$pr" "$material"; then
        printf 'unchanged\n'
        return 0
    fi

    # The bundle's structural merge gate makes a rejected lease safe to
    # tolerate for read-only/reviewer work, but degraded work is never persisted
    # as successfully handled. Genuine contention still skips this tick.
    "${SCRIPT_DIR}/loop_lock.sh" acquire "$pr" 2> /dev/null || lock_rc=$?
    case "$lock_rc" in
        0) : ;;
        1)
            err "#$pr: locked — skipping (lease genuinely held by another run)"
            printf 'skip\n'
            return 0
            ;;
        2)
            err "#$pr: cross-host lease unavailable (label backend rejected the add)" \
                "— proceeding WITHOUT it (degraded, not contended; duplicate" \
                "run-gate work is possible, but no irreversible action can" \
                "result since merge is hard-gated in this bundle)"
            lock_degraded=1
            ;;
        *)
            err "#$pr: lease acquisition failed unexpectedly (exit=${lock_rc})"
            return 12
            ;;
    esac
    # shellcheck disable=SC2064
    trap "'${SCRIPT_DIR}/loop_lock.sh' release '$pr' >/dev/null 2>&1" RETURN

    # Close the pre-lease race. Another worker may have processed this exact
    # transition while we waited; only the state re-read under the lease decides.
    material="$(collect_fingerprint_material "$pr")" || return 13
    if fingerprint_state_matches "$pr" "$material"; then
        printf 'unchanged\n'
        return 0
    fi

    sig="$(cmd_signals "$pr")" || {
        err "#$pr: signal observation failed"
        return 13
    }
    head_sha="$(printf '%s' "$sig" | _jget head_sha 2> /dev/null)" || {
        err "#$pr: signal payload was invalid"
        return 13
    }
    d="$(printf '%s' "$sig" | "${SCRIPT_DIR}/merge_decision.sh" decide)" || {
        err "#$pr: merge decision failed"
        return 13
    }
    act="$(printf '%s' "$d" | _jget action 2> /dev/null)" || {
        err "#$pr: merge decision was invalid"
        return 13
    }
    [[ -n "$act" ]] || {
        err "#$pr: merge decision omitted action"
        return 13
    }

    # Cheap signals clear → run the expensive verification gate once.
    if [[ "$act" == "run-gate" ]]; then
        gate="$("${SCRIPT_DIR}/verification_gate.sh" review "$pr" 2> /dev/null)" || {
            gate='{"reviewer_error":true,"tier1":{"passed":false},"consensus_score":0}'
            handling_failed=1
        }
        sig2="$(printf '%s' "$sig" | python3 -c '
import json,sys
s=json.load(sys.stdin)
try:
    g=json.loads(sys.argv[1])
    if not isinstance(g,dict):
        raise ValueError()
except Exception:
    g={"reviewer_error":True}
ok=(g.get("tier1") or {}).get("passed") is True and not g.get("reviewer_error")
s["gate_tier1"]="pass" if ok else "fail"
s["reviewer_error"]=bool(g.get("reviewer_error"))
print(json.dumps(s))' "$gate" 2> /dev/null)" || {
            err "#$pr: review gate returned an invalid envelope"
            return 13
        }
        [[ "$(printf '%s' "$sig2" | _jget reviewer_error 2> /dev/null)" != "True" ]] || handling_failed=1
        d="$(printf '%s' "$sig2" | "${SCRIPT_DIR}/merge_decision.sh" decide)" || {
            err "#$pr: post-review decision failed"
            return 13
        }
        act="$(printf '%s' "$d" | _jget action 2> /dev/null)" || return 13
    fi

    case "$act" in
        merge)
            if ! lifecycle_gate_ok "$pr"; then
                err "#$pr: lifecycle gate unsatisfied (audit drift) → needs-human (SC-011)"
                apply_label "$pr" needs-human || handling_failed=1
                act="hand-human"
            else
                rc=0
                cmd_merge "$pr" "$head_sha" || rc=$?
                if [[ $rc -eq 9 ]]; then
                    apply_label "$pr" ready-to-merge || handling_failed=1
                elif [[ $rc -eq 78 ]]; then
                    # The portable copy uses this structural hard gate. Keeping
                    # it here lets both maintained implementations share the
                    # transition machinery without weakening that gate.
                    apply_label "$pr" needs-human || handling_failed=1
                elif [[ $rc -eq 0 ]]; then
                    if [[ "$APPLY" == "1" ]]; then
                        cmd_post_merge_check "$LAST_MERGE_SHA" > /dev/null 2>&1 || {
                            err "#$pr merged → main RED/pending — HALT"
                            act="halt"
                            handling_failed=1
                        }
                    fi
                else
                    err "#$pr: merge action failed (exit ${rc})"
                    apply_label "$pr" needs-human || true
                    handling_failed=1
                fi
            fi
            ;;
        update-branch)
            if ! gh_op update-branch "$pr" > /dev/null 2>&1; then
                err "#$pr: update-branch action failed"
                apply_label "$pr" needs-human || true
                handling_failed=1
            fi
            ;;
        hand-human)
            apply_label "$pr" "$(printf '%s' "$d" | _jget label)" || handling_failed=1
            ;;
        halt)
            err "#$pr: HALT (post-merge main breakage)"
            handling_failed=1
            ;;
        revise) err "#$pr: revise — the skill runs /pr-address-comments, /project-verify, /pr-review" ;;
        wait) err "#$pr: waiting on checks/mergeability" ;;
        *)
            err "#$pr: unsupported decision action '$act'"
            return 13
            ;;
    esac

    # Audit remains fail-open, but only changed material reaches it.
    "${SCRIPT_DIR}/audit_log.sh" append \
        "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"pr\":${pr},\"action\":\"${act}\",\"apply\":${APPLY}}" \
        2> /dev/null || true

    if ((handling_failed == 1)); then
        err "#$pr: handling/review failure — transition state not recorded"
        printf '%s\n' "$act"
        [[ "$act" == "halt" ]] && return 0
        return 13
    fi
    if ((lock_degraded == 1)); then
        err "#$pr: degraded lease — transition state not recorded"
        printf '%s\n' "$act"
        return 0
    fi

    # Only certify the handled transition if head/check/review material stayed
    # stable through dispatch. Local disposition/action-label effects are
    # incorporated by persisting the fresh full fingerprint.
    post_material="$(collect_fingerprint_material "$pr")" || return 13
    if ! fingerprint_external_matches "$material" "$post_material"; then
        err "#$pr: external transition occurred during dispatch — state not recorded"
        printf '%s\n' "$act"
        return 0
    fi
    persist_fingerprint_state "$pr" "$post_material" "$act" || {
        err "#$pr: atomic fingerprint state write failed"
        printf '%s\n' "$act"
        return 13
    }
    printf '%s\n' "$act"
}

# --- bounded state-driven loop. Every managed PR is observed each pass, while
# expensive handling only runs for changed fingerprints. The first complete
# pass with no changed/actionable PR stops immediately.
cmd_run() {
    local ceiling="${PR_MERGE_LOOP_CEILING_SEC:-600}" poll="${PR_MERGE_LOOP_POLL_SEC:-30}"
    local start deadline now managed_json managed pr act rc changed complete
    gh_op fp-scope > /dev/null || {
        err "material fingerprinting unsupported for this repository/provider"
        return 13
    }
    start="$(_now)"
    deadline=$((start + ceiling))
    while :; do
        now="$(_now)"
        ((now < deadline)) || break
        managed_json="$(cmd_list_managed)" || return $?
        managed="$(printf '%s' "$managed_json" | python3 -c '
import json,sys
items=json.load(sys.stdin)
if not isinstance(items,list):
    raise ValueError("managed list")
numbers=[]
for item in items:
    number=item.get("number") if isinstance(item,dict) else None
    if not isinstance(number,int) or number < 1:
        raise ValueError("managed PR number")
    numbers.append(str(number))
print(" ".join(numbers))' 2> /dev/null)" || {
            err "managed-PR observation was malformed"
            return 13
        }
        changed=0
        complete=1
        # shellcheck disable=SC2086 # space-joined validated integer PR numbers
        for pr in $managed; do
            now="$(_now)"
            if ((now >= deadline)); then
                complete=0
                break
            fi
            rc=0
            act="$(cmd_tick "$pr")" || rc=$?
            [[ $rc -eq 0 ]] || return "$rc"
            case "$act" in
                halt)
                    err "loop HALT — main breakage on #$pr"
                    return 11
                    ;;
                unchanged) : ;;
                *) changed=1 ;;
            esac
        done
        ((complete == 1)) || break
        now="$(_now)"
        ((now < deadline)) || break
        if ((changed == 0)); then
            cmd_empty_run reset > /dev/null
            cmd_empty_run incr > /dev/null
            err "first unchanged pass — stopping"
            break
        fi
        cmd_empty_run reset > /dev/null
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
