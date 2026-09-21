# shellcheck shell=bash
# pr_merge_loop_gh.sh — platform I/O layer for pr_merge_loop.sh (gh/glab reads, GraphQL
# review-thread pagination, and the human-blocking-thread classifier).
#
# Split out of pr_merge_loop.sh (C-SIZE/CON-002, ceiling 600) along the
# platform-I/O-vs-decision seam: everything here talks to the code host (gh, glab,
# GraphQL) and returns raw or lightly-classified values; nothing here decides whether
# to merge. Sourced, not executed — depends on the caller having already defined
# SCRIPT_DIR, STATE_DIR, AUTHORS_FILE, err(), and _net() (see pr_merge_loop.sh).
#
# shellcheck shell=bash

# --- platform seam (default drives native gh) ---
gh_op() {
    # A disposition the reviewing agent recorded via set-disposition wins over the live default.
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
    if [[ "$platform" == "gitlab" ]]; then
        case "$op" in
            fp-scope | fp-view | fp-checks | fp-threads)
                err "state fingerprinting is unsupported for provider gitlab"
                return 13
                ;;
            list) glab mr list -F json 2> /dev/null ;;
            checks) glab ci status 2> /dev/null ;;
            author) glab mr view "$pr" -F json 2> /dev/null | python3 -c 'import json,sys;print((json.load(sys.stdin).get("author") or {}).get("username",""))' 2> /dev/null ;;
            admin-check) echo false ;;
            do-merge)
                err "gitlab auto-merge not implemented — fail closed"
                return 1
                ;;
            *) echo "" ;;
        esac
        return $?
    fi
    case "$op" in
        fp-scope) _repository_scope_json ;;
        fp-view)
            _net gh pr view "$pr" \
                --json headRefOid,baseRefName,mergeable,mergeStateStatus,reviewDecision,latestReviews,labels,isDraft,state \
                2> /dev/null
            ;;
        fp-checks) _github_fp_checks "$pr" ;;
        fp-threads) gh_threads_raw "$pr" ;;
        list) gh pr list --json number,author 2> /dev/null ;;
        checks) _github_fp_checks "$pr" | python3 -c 'import json,sys;print("\n".join(str(item["bucket"]) for item in json.load(sys.stdin)))' ;;
        reviewdecision) gh pr view "$pr" --json reviewDecision -q '.reviewDecision' 2> /dev/null ;;
        unresolved-human) count_unresolved_human "$pr" ;;
        disposition) echo keep ;;
        mergeable) gh pr view "$pr" --json mergeable,mergeStateStatus -q '.mergeable+" "+.mergeStateStatus' 2> /dev/null ;;
        hold) _github_hold "$pr" ;;
        author) gh pr view "$pr" --json author -q '.author.login' 2> /dev/null ;;
        admin-check) gh api "repos/$(_owner_repo_from_remote)" -q '.permissions.admin' 2> /dev/null || echo false ;;
        protection) gh api "repos/$(_owner_repo_from_remote)/branches/$(gh_op basebranch "$pr")/protection" -q '"enforce_admins="+(.enforce_admins.enabled|tostring)+" required_signatures="+(.required_signatures.enabled|tostring)+" merge_queue=false"' 2> /dev/null || echo "PROTECTION_LOOKUP_FAILED" ;;
        update-branch) gh pr update-branch "$pr" 2>&1 ;;
        add-label) gh issue edit "$pr" --add-label "${3:?label required}" 2>&1 ;;
        do-merge) gh pr merge "$pr" --squash --admin --delete-branch 2>&1 ;;
        headsha) gh pr view "$pr" --json headRefOid -q '.headRefOid' 2> /dev/null ;;
        basebranch) gh pr view "$pr" --json baseRefName -q '.baseRefName' 2> /dev/null ;;
        mergecommit) gh pr view "$pr" --json mergeCommit -q '.mergeCommit.oid // empty' 2> /dev/null ;;
        *)
            err "unsupported GitHub operation: $op"
            return 64
            ;;
    esac
}

_repository_scope_json() {
    local url
    url="$(git remote get-url origin 2> /dev/null)" || return 1
    python3 - "$url" <<'PY'
import json
import re
import sys
from urllib.parse import urlsplit

url = sys.argv[1].strip()
if "://" in url:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    path = parsed.path
else:
    match = re.fullmatch(r"(?:[^@]+@)?([^:]+):(.+)", url)
    if not match:
        raise SystemExit(1)
    host, path = match.groups()
path = path.strip("/")
if path.endswith(".git"):
    path = path[:-4]
parts = path.split("/")
if not host or len(parts) != 2 or not all(parts):
    raise SystemExit(1)
print(json.dumps({"host": host, "owner_repo": "/".join(parts)}, separators=(",", ":")))
PY
}

_github_fp_checks() {
    local pr="${1:?pr required}" raw rc=0
    raw="$(_net gh pr checks "$pr" \
        --json name,bucket,state,link,startedAt,completedAt 2> /dev/null)" || rc=$?
    case "$rc" in
        0 | 1 | 8) ;;
        *) return "$rc" ;;
    esac
    printf '%s' "$raw" | python3 -c '
import json,sys
value=json.load(sys.stdin)
if not isinstance(value,list):
    raise ValueError("checks")
print(json.dumps(value,separators=(",",":")))' 2> /dev/null
}

_github_hold() {
    local pr="${1:?pr required}" raw
    raw="$(_net gh pr view "$pr" --json labels 2> /dev/null)" || return $?
    printf '%s' "$raw" | python3 -c '
import json,sys
labels=json.load(sys.stdin).get("labels")
if not isinstance(labels,list):
    raise ValueError("labels")
print("true" if any(isinstance(item,dict) and item.get("name")=="hold" for item in labels) else "false")' \
        2> /dev/null
}

# Derive "owner/repo" from the origin remote via pure git (no API call) —
# precedence: git > api. Handles both https and scp-like ssh remote forms.
_owner_repo_from_remote() {
    _repository_scope_json | python3 -c '
import json,sys
print(json.load(sys.stdin)["owner_repo"],end="")' 2> /dev/null
}

# SECURITY (finding 3): a bot-started thread with a LATER human objection must
# still block, and truncated pagination must never silently under-count. Emits
# one JSON page per line (NDJSON) — thread-level AND per-thread comment-level
# pagination, so a caller sees every comment on every thread, not just the
# first of each. Seam: PR_MERGE_LOOP_THREADS_JSON (offline tests) short-circuits
# to a single page.
#
# github-only: GitHub's reviewThreads (isResolved/isOutdated per-thread) has no
# clean GitLab twin (tested directly via PR_MERGE_LOOP_THREADS_JSON in
# pr_merge_loop.bats). unresolved-human is never reached on the gitlab path
# (fails closed via admin-check=false before this matters).
GH_THREADS_PAGE_CAP=50 # first:100 threads/page -> 5000 threads before failing closed
gh_threads_raw() {
    if [[ -n "${PR_MERGE_LOOP_THREADS_JSON:-}" ]]; then
        printf '%s\n' "$PR_MERGE_LOOP_THREADS_JSON"
        return 0
    fi
    local pr="${1:?pr required}" nwo owner repo cursor="" page=0 resp next has_more endc
    nwo="$(_owner_repo_from_remote)" || return 1
    owner="${nwo%%/*}"
    repo="${nwo##*/}"
    # shellcheck disable=SC2016  # $owner/$repo/$pr/$cursor are GraphQL variables
    local query='
      query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
        repository(owner:$owner,name:$repo){
          pullRequest(number:$pr){
            reviewThreads(first:100, after:$cursor){
              pageInfo{ hasNextPage endCursor }
              nodes{
                id isResolved isOutdated
                comments(first:50){ pageInfo{ hasNextPage } nodes{ id createdAt author{ login } } }
                latestComments:comments(last:1){ nodes{ id createdAt } }
              }}}}}'
    while :; do
        page=$((page + 1))
        if ((page > GH_THREADS_PAGE_CAP)); then
            err "#$pr: review-thread pagination exceeded ${GH_THREADS_PAGE_CAP} pages — fail closed"
            return 1
        fi
        if [[ -n "$cursor" ]]; then
            resp="$(_net gh api graphql -F owner="$owner" -F repo="$repo" -F pr="$pr" -F cursor="$cursor" -f query="$query" 2> /dev/null)"
        else
            resp="$(_net gh api graphql -F owner="$owner" -F repo="$repo" -F pr="$pr" -f query="$query" 2> /dev/null)"
        fi
        [[ -n "$resp" ]] || return 1
        printf '%s\n' "$resp"
        next="$(printf '%s' "$resp" | python3 -c '
import json, sys
try:
    pi = json.load(sys.stdin)["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]
    print(("1" if pi.get("hasNextPage") else "0") + "\t" + (pi.get("endCursor") or ""))
except Exception:
    print("ERR")
' 2> /dev/null)"
        [[ "$next" != "ERR" && -n "$next" ]] || return 1
        has_more="${next%%$'\t'*}"
        endc="${next#*$'\t'}"
        [[ "$has_more" == "1" ]] || break
        [[ -n "$endc" ]] || return 1
        cursor="$endc"
    done
    return 0
}

# Count review threads that BLOCK on a human: unresolved, non-outdated, and with
# ANY comment (not just the first) from an author outside the bot allowlist — a
# bot-opened thread with a later human objection must count. A thread whose
# comments were truncated by the 50-comment page cap is treated as blocking
# (cannot rule out a human deeper in it). Any parse failure across any page ->
# fail closed (print 1).
COUNT_UH_PY='
import json, sys
try:
    cfg = json.load(open(sys.argv[1])) or {}
except Exception:
    cfg = {}
bots = {a.lower().replace("[bot]", "") for a in (cfg.get("authors") or [])}

def fail_closed():
    print(1)
    sys.exit(0)

lines = [ln for ln in sys.stdin.read().splitlines() if ln.strip()]
if not lines:
    fail_closed()
nodes = []
for ln in lines:
    try:
        page_nodes = json.loads(ln)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        if not isinstance(page_nodes, list):
            raise ValueError("nodes not a list")
    except Exception:
        fail_closed()
    nodes.extend(page_nodes)

count = 0
for t in nodes:
    if t.get("isResolved") or t.get("isOutdated"):
        continue
    comments = (t.get("comments") or {})
    cs = comments.get("nodes") or []
    blocking = bool((comments.get("pageInfo") or {}).get("hasNextPage")) or not cs
    for c in cs:
        login = ((c.get("author") or {}).get("login") or "")
        if login.lower().replace("[bot]", "") not in bots:
            blocking = True
            break
    if blocking:
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
