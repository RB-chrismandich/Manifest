# shellcheck shell=bash
# pr_merge_loop_fp.sh — observation & transition-state layer for
# pr_merge_loop.sh (signal collection, managed-PR listing, counters,
# canonical material fingerprinting, and durable fingerprint state).
#
# Split out of pr_merge_loop.sh (C-SIZE/CON-002, ceiling 600) along the
# observation/state seam, complementing lib/pr_merge_loop_gh.sh's platform-I/O
# layer: everything here observes inputs, canonicalizes them into digest-only
# material, or persists per-PR transition state under STATE_DIR; nothing here
# acts on a decision. Sourced, not executed — depends on the caller having
# already defined STATE_DIR, AUTHORS_FILE, APPLY, err(), _net(),
# _observed_at(), and (via lib/pr_merge_loop_gh.sh) gh_op and
# _owner_repo_from_remote (see pr_merge_loop.sh).
#
# shellcheck shell=bash

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
    if [[ $rc -eq 0 ]]; then gh_op fp-view "$pr" > "$tmp/view" || rc=$?; fi
    if [[ $rc -eq 0 ]]; then gh_op fp-checks "$pr" > "$tmp/checks" || rc=$?; fi
    if [[ $rc -eq 0 ]]; then gh_op fp-threads "$pr" > "$tmp/threads" || rc=$?; fi
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
    python3 - "$path" "$fingerprint" << 'PY' 2> /dev/null
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
    python3 - "$path" "$fingerprint" "$action" "$observed" << 'PY'
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
