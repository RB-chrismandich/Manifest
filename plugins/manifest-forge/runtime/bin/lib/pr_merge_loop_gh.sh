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
        checks) "${SCRIPT_DIR}/git_ops.sh" pr-checks "$pr" --json bucket -q '.[].bucket' 2> /dev/null ;;
        reviewdecision) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json reviewDecision -q '.reviewDecision' 2> /dev/null ;;
        unresolved-human) count_unresolved_human "$pr" ;;
        disposition) echo keep ;;
        mergeable) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json mergeable,mergeStateStatus -q '.mergeable+" "+.mergeStateStatus' 2> /dev/null ;;
        verify) echo pass ;;
        hold) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json labels -q '.labels[].name' 2> /dev/null | grep -qx hold && echo true || echo false ;;
        author) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json author -q '.author.login' 2> /dev/null ;;
        admin-check) "${SCRIPT_DIR}/git_ops.sh" repo-admin-check 2> /dev/null || echo false ;;
        # SECURITY (finding 2): a protection LOOKUP failure must never read as
        # "no protection" (the opposite of fail-closed) — surface a sentinel that
        # cmd_merge's own check below treats as blocking, instead of silently
        # defaulting to all-flags-false.
        protection) "${SCRIPT_DIR}/git_ops.sh" branch-protection 2> /dev/null || echo "PROTECTION_LOOKUP_FAILED" ;;
        update-branch) "${SCRIPT_DIR}/git_ops.sh" pr-update-branch "$pr" 2>&1 ;;
        do-merge) "${SCRIPT_DIR}/git_ops.sh" pr-merge "$pr" --squash --admin --delete-branch 2>&1 ;;
        headsha) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json headRefOid -q '.headRefOid' 2> /dev/null ;;
        basebranch) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json baseRefName -q '.baseRefName' 2> /dev/null ;;
        mergecommit) "${SCRIPT_DIR}/git_ops.sh" pr-view "$pr" --json mergeCommit -q '.mergeCommit.oid // empty' 2> /dev/null ;;
    esac
}

# Derive "owner/repo" from the origin remote via pure git (no API call) —
# precedence: git > api. Handles both https and scp-like ssh remote forms.
_owner_repo_from_remote() {
    local url path
    url="$(git remote get-url origin 2> /dev/null)" || return 1
    url="${url%.git}"
    url="${url#*://}" # strip scheme (https://, ssh://)
    url="${url#*@}"   # strip user@ (scp-like ssh: git@host:owner/repo)
    path="${url#*[:/]}"
    [[ -n "$path" && "$path" == */* ]] || return 1
    printf '%s' "$path"
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
                isResolved isOutdated
                comments(first:50){ pageInfo{ hasNextPage } nodes{ author{ login } } }
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
