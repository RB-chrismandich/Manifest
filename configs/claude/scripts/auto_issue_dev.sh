#!/usr/bin/env bash
# auto_issue_dev.sh - selection/dependency/flagging engine for /auto-issue-dev
#
# Wraps git_ops.sh. Picks the next opted-in ('auto-dev') issue that is ready to
# develop, skipping (and tagging) ones with unmet dependencies. Failure/dependency
# flagging is fail-open.
#
# Subcommands:
#   next-issue [--json]        First READY auto-dev issue; exit 3 when none
#   check-deps <N> [--json]    Exit 2 if unmet deps; exit 1 if N missing
#   mark-blocked <N> <reason>  Add needs-human label + deduped comment (exit 0)
#   mark-dependency <N> <refs> Add blocked-dependency label + deduped comment (exit 0)
#
# Env seams: GIT_OPS_BIN, GIT_PLATFORM_BIN, AUTO_ISSUE_DEV_LABEL,
#            AUTO_ISSUE_DEV_DEP_LABEL, AUTO_ISSUE_DEV_FAIL_LABEL

set -euo pipefail

err() { echo "auto-issue-dev: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_OPS_BIN="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
GIT_PLATFORM_BIN="${GIT_PLATFORM_BIN:-${SCRIPT_DIR}/git_platform.sh}"
DEV_LABEL="${AUTO_ISSUE_DEV_LABEL:-auto-dev}"
DEP_LABEL="${AUTO_ISSUE_DEV_DEP_LABEL:-blocked-dependency}"
FAIL_LABEL="${AUTO_ISSUE_DEV_FAIL_LABEL:-needs-human}"

git_ops() { "${GIT_OPS_BIN}" "$@"; }

# detect_platform — echo github|gitlab|git (via git_platform.sh)
detect_platform() {
    bash "${GIT_PLATFORM_BIN}" 2>/dev/null || { err "platform detection failed; defaulting to 'git' (gh-style calls may fail)"; printf 'git'; }
}

# Normalize an issue-view payload (gh or glab JSON) into a stable shape:
#   {"number","title","body","state","labels":[names],"comments":[bodies]}
# Reads raw JSON on stdin; emits "{}" on parse failure. Mirrors the field
# mapping in issue_support.sh's NORMALIZE_PY (number/iid, opened→open,
# description→body, label objects/strings→names, comments). The GitLab notes
# fold is handled here too: when NORMALIZE_NOTES is set in the environment its
# text is appended as a trailing comment (no-op when unset, i.e. the gh path).
# NOTE: `python3 -c` (not a heredoc) keeps the piped JSON on stdin.
NORMALIZE_ISSUE_PY='
import sys, json, os
try:
    d = json.load(sys.stdin)
except Exception:
    print("{}"); sys.exit(0)
if not isinstance(d, dict):
    print("{}"); sys.exit(0)
num = d.get("number") or d.get("iid") or d.get("id") or 0
title = d.get("title") or ""
body = d.get("body")
if body is None:
    body = d.get("description") or ""
state = (d.get("state") or "").lower()
if state == "opened":
    state = "open"
labels = []
for L in (d.get("labels") or []):
    labels.append(L.get("name", "") if isinstance(L, dict) else str(L))
labels = [n for n in labels if n]
comments = []
src = d.get("comments")
if src is None:
    src = d.get("notes") or []
for c in (src or []):
    if isinstance(c, dict):
        comments.append(c.get("body", "") or "")
    else:
        comments.append(str(c))
notes = os.environ.get("NORMALIZE_NOTES", "")
if notes:
    comments.append(notes)
print(json.dumps({"number": num, "title": title, "body": body,
                  "state": state, "labels": labels, "comments": comments},
                 separators=(",", ":")))
'

# issue_json <N> — fetch issue N and emit the normalized JSON object (or "{}").
# Platform-aware: github via --json fields, gitlab via --output json (+ notes).
issue_json() {
    local n="$1" platform raw="" notes=""
    platform="$(detect_platform)"
    if [[ "${platform}" == "gitlab" ]]; then
        raw="$(git_ops issue-view "${n}" --output json 2>/dev/null || true)"
        [[ -z "${raw}" ]] && { err "issue-view #${n} returned no data (tracker outage/auth?); treating as unreadable"; printf '{}'; return 0; }
        # glab `issue view --output json` does not embed notes; fetch text and
        # fold each comment in (via NORMALIZE_NOTES) so has_marker() can scan them.
        notes="$(git_ops issue-view "${n}" --comments 2>/dev/null || true)"
        printf '%s' "${raw}" | NORMALIZE_NOTES="${notes}" python3 -c "${NORMALIZE_ISSUE_PY}" 2>/dev/null || printf '{}'
    else
        raw="$(git_ops issue-view "${n}" --json number,title,body,state,labels,comments 2>/dev/null || true)"
        [[ -z "${raw}" ]] && { err "issue-view #${n} returned no data (tracker outage/auth?); treating as unreadable"; printf '{}'; return 0; }
        printf '%s' "${raw}" | python3 -c "${NORMALIZE_ISSUE_PY}" 2>/dev/null || printf '{}'
    fi
}

usage() {
    cat <<'USAGE'
Usage: auto_issue_dev.sh <subcommand> [args]

  next-issue [--json]          First READY auto-dev issue; exit 3 when none
  check-deps <N> [--json]      Exit 2 if unmet deps; exit 1 if N missing
  mark-blocked <N> <reason>    Add needs-human label + deduped comment
  mark-dependency <N> <refs>   Add blocked-dependency label + deduped comment

Fail-open: mark-* always exit 0. Opt-in label: auto-dev.
USAGE
}

# parse_dep_refs <text> — print unique dependency issue/PR numbers, one per line
parse_dep_refs() {
    python3 - "$1" <<'PY'
import sys, re
text = sys.argv[1] or ""
pat = re.compile(r'(?:depends on|blocked by|requires|needs)\s+#(\d+)', re.IGNORECASE)
seen = []
for m in pat.finditer(text):
    n = m.group(1)
    if n not in seen:
        seen.append(n)
print("\n".join(seen))
PY
}

# ref_met <M> — return 0 if referenced issue is closed OR PR is merged, else 1.
# State is normalized (GitLab 'opened'→open is unmet; 'closed'/'merged' met).
ref_met() {
    local m="$1" view state merged
    view="$(issue_json "$m" 2>/dev/null || true)"
    state="$(printf '%s' "${view}" | python3 -c 'import sys,json
try: d=json.load(sys.stdin)
except Exception: d={}
print((d.get("state") or "").lower())' 2>/dev/null || true)"
    if [[ -n "${state}" ]]; then
        # normalized: opened→open already; closed/merged are "met"
        [[ "${state}" == "closed" || "${state}" == "merged" ]] && return 0
        return 1
    fi
    # Fall back to PR view (ref may be a PR number); request JSON per platform.
    local platform; platform="$(detect_platform)"
    if [[ "${platform}" == "gitlab" ]]; then
        view="$(git_ops pr-view "$m" --output json 2>/dev/null || true)"
    else
        view="$(git_ops pr-view "$m" --json state,merged 2>/dev/null || true)"
    fi
    [[ -z "${view}" ]] && { err "could not resolve ref #${m} (issue+pr view both empty); treating as UNMET"; return 1; }
    merged="$(printf '%s' "${view}" | python3 -c 'import sys,json
try: d=json.load(sys.stdin)
except Exception: d={}
st=(d.get("state") or "").lower()
print("yes" if (d.get("merged") or st=="merged") else "no")' 2>/dev/null || echo no)"
    [[ "${merged}" == "yes" ]]
}

# cmd_check_deps <N> [--json]
cmd_check_deps() {
    local n="${1:-}"; local json=0; [[ "${2:-}" == "--json" ]] && json=1
    [[ -n "${n}" ]] || { err "check-deps: issue number required"; return 1; }
    local body refs unmet=()
    body="$(issue_json "${n}" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print((d.get("title") or "")+" \n "+(d.get("body") or ""))
except Exception: pass' || true)"
    refs="$(parse_dep_refs "${body}")"
    local m
    while IFS= read -r m; do
        [[ -z "${m}" || "${m}" == "${n}" ]] && continue
        ref_met "${m}" || unmet+=("${m}")
    done <<< "${refs}"
    if [[ ${#unmet[@]} -eq 0 ]]; then
        [[ ${json} -eq 1 ]] && echo '{"unmet":[]}'
        return 0
    fi
    if [[ ${json} -eq 1 ]]; then
        printf '{"unmet":[%s]}\n' "$(IFS=,; echo "${unmet[*]}")"  # array-safe: non-empty (early-returned above)
    else
        printf 'unmet dependencies for #%s: %s\n' "${n}" "$(printf '#%s ' "${unmet[@]}")"  # array-safe: non-empty (early-returned above)
    fi
    return 2
}

# has_marker <N> <marker> — 0 if a comment with marker already exists
has_marker() {
    local n="$1" marker="$2" body
    body="$(issue_json "${n}" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    print("\n".join(str(c) for c in (d.get("comments") or [])))
except Exception: pass' || true)"
    [[ "${body}" == *"${marker}"* ]]
}

# flag <N> <label> <marker> <comment-body> — add label + deduped comment (fail-open)
flag() {
    local n="$1" label="$2" marker="$3" comment="$4"
    [[ -n "${n}" ]] || { err "flag: issue number required"; return 0; }
    git_ops issue-edit "${n}" --add-label "${label}" >/dev/null 2>&1 \
        || err "FAILED to add '${label}' to #${n} — loop filters by label, so #${n} will be re-selected every run (is the label provisioned? run label_sync.sh)"
    if has_marker "${n}" "${marker}"; then
        return 0
    fi
    # Mirror issue_support.sh: pass the body inline via --body (gitlab note +
    # github comment both accept it through git_ops). Marker leads so dedup
    # via has_marker() matches on the next run.
    git_ops issue-comment "${n}" --body "${marker}"$'\n\n'"${comment}" >/dev/null 2>&1 \
        || err "could not comment on #${n} (continuing)"
    return 0
}

cmd_mark_blocked() {
    local n="${1:-}" reason="${2:-unspecified}"
    flag "${n}" "${FAIL_LABEL}" "<!-- auto-issue-dev:blocked -->" \
        "Auto-dev could not complete this issue: ${reason}. Flagged \`${FAIL_LABEL}\` for a human."
    return 0
}

cmd_mark_dependency() {
    local n="${1:-}" refs="${2:-}"
    flag "${n}" "${DEP_LABEL}" "<!-- auto-issue-dev:dependency -->" \
        "Skipped by auto-dev: unmet dependency ${refs}. Will retry once the blocker merges and the \`${DEP_LABEL}\` label is removed."
    return 0
}

# cmd_next_issue [--json]
cmd_next_issue() {
    local json=0; [[ "${1:-}" == "--json" ]] && json=1
    local platform raw list
    platform="$(detect_platform)"
    if [[ "${platform}" == "gitlab" ]]; then
        if ! raw="$(git_ops issue-list --state open --label "${DEV_LABEL}" --output json 2>/dev/null)"; then
            err "issue-list failed (tracker outage/auth?); treating as empty queue — loop may stop prematurely"
            raw='[]'
        fi
    else
        if ! raw="$(git_ops issue-list --state open --label "${DEV_LABEL}" --json number,title,url,labels 2>/dev/null)"; then
            err "issue-list failed (tracker outage/auth?); treating as empty queue — loop may stop prematurely"
            raw='[]'
        fi
    fi
    [[ -z "${raw}" ]] && raw='[]'
    # Normalize each list item to {number,title,url,labels:[names]} so the
    # downstream filter/sort works identically for gh and glab (iid→number,
    # web_url→url, label objects/strings→names).
    list="$(printf '%s' "${raw}" | python3 -c 'import sys,json
try: items=json.load(sys.stdin)
except Exception: items=[]
if not isinstance(items, list): items=[]
out=[]
for i in items:
    if not isinstance(i, dict): continue
    num=i.get("number") or i.get("iid") or i.get("id") or 0
    url=i.get("url") or i.get("web_url") or ""
    names=[]
    for L in (i.get("labels") or []):
        names.append(L.get("name","") if isinstance(L,dict) else str(L))
    out.append({"number":num,"title":i.get("title",""),"url":url,
                "labels":[{"name":n} for n in names if n]})
print(json.dumps(out,separators=(",",":")))' 2>/dev/null || echo '[]')"
    [[ -z "${list}" ]] && list='[]'

    # Candidate numbers, ascending (oldest-first ~= lowest number), that are NOT
    # already tagged DEP_LABEL. Also count those excluded for that reason.
    local cand skipped_other
    cand="$(printf '%s' "${list}" | python3 -c 'import sys,json
dep=sys.argv[1]
try: items=json.load(sys.stdin)
except Exception: items=[]
if not isinstance(items, list): items=[]
ok=[i for i in items if dep not in {l["name"] for l in (i.get("labels") or [])}]
ok.sort(key=lambda i:i["number"])
print(" ".join(str(i["number"]) for i in ok))' "${DEP_LABEL}")"
    skipped_other="$(printf '%s' "${list}" | python3 -c 'import sys,json
dep=sys.argv[1]
try: items=json.load(sys.stdin)
except Exception: items=[]
if not isinstance(items, list): items=[]
print(sum(1 for i in items if dep in {l["name"] for l in (i.get("labels") or [])}))' "${DEP_LABEL}")"

    local skipped_dependency=0 n out refs meta
    # shellcheck disable=SC2086  # intentional: splitting space-separated number list
    for n in ${cand}; do
        if out="$(cmd_check_deps "${n}" --json)"; then
            : # ready
        else
            # unmet deps -> tag + skip
            refs="$(printf '%s' "${out}" | python3 -c 'import sys,json
try: u=json.load(sys.stdin).get("unmet",[])
except Exception: u=[]
print(" ".join("#%s"%x for x in u))' 2>/dev/null || true)"
            cmd_mark_dependency "${n}" "${refs}"
            skipped_dependency=$((skipped_dependency + 1))
            continue
        fi
        # ready candidate n — emit and exit 0 (reuse the already-fetched list;
        # same snapshot avoids a second API call and a stale-read race)
        meta="$(printf '%s' "${list}" | python3 -c 'import sys,json
n=int(sys.argv[1]); sk=int(sys.argv[2])
try: items=json.load(sys.stdin)
except Exception: items=[]
if not isinstance(items, list): items=[]
m=next((i for i in items if i["number"]==n), {"number":n,"title":"","url":""})
print(json.dumps({"number":m["number"],"title":m.get("title",""),"url":m.get("url",""),"skipped_dependency":sk},separators=(",",":")))' "${n}" "${skipped_dependency}")"
        if [[ ${json} -eq 1 ]]; then echo "${meta}"; else echo "${n}"; fi
        return 0
    done

    # none ready
    if [[ ${json} -eq 1 ]]; then
        printf '{"ready":0,"skipped_dependency":%s,"skipped_other":%s}\n' \
            "${skipped_dependency}" "${skipped_other:-0}"
    else
        err "no ready auto-dev issues (skipped ${skipped_dependency} for deps)"
    fi
    return 3
}

main() {
    local sub="${1:-}"; shift || true
    case "${sub}" in
        --help|-h|help) usage; exit 0 ;;
        check-deps) cmd_check_deps "$@"; exit $? ;;
        mark-blocked) cmd_mark_blocked "$@"; exit 0 ;;
        mark-dependency) cmd_mark_dependency "$@"; exit 0 ;;
        next-issue) cmd_next_issue "$@"; exit $? ;;
        *) err "unknown subcommand: ${sub:-<none>}"; usage >&2; exit 64 ;;
    esac
}

main "$@"
