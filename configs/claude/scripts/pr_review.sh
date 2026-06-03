#!/usr/bin/env bash
# pr_review.sh - Triage all open pull/merge requests (analysis-only)
#
# Enumerates every open PR on the active platform (GitHub via gh, GitLab via
# glab), assesses mergeability / checks / staleness / superseded status, and
# recommends a disposition per PR. Performs NO mutations.
#
# Usage: pr_review.sh [--platform github|gitlab] [--stale-days N] [--json]
#
# Resolution: by default fetches via the platform CLI. Set PR_REVIEW_FETCH to an
# executable that prints a normalized JSON array (see fields below) to override
# fetching (used by tests / custom integrations). Each element:
#   {number,title,author,updated(ISO8601),mergeable(CLEAN|CONFLICTING|UNKNOWN),
#    checks(PASS|FAIL|PENDING|NONE),draft(bool),head(str),merged(bool)}
#
# Exit codes: 0 = success (incl. empty queue); 2 = usage / platform / auth error.
#
# Compatible with bash 3.2.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PLATFORM=""
STALE_DAYS=30
JSON_OUT=false

err() { echo "pr-review: $*" >&2; }
usage_error() { err "$*"; exit 2; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) [[ $# -ge 2 ]] || usage_error "--platform needs an argument"; PLATFORM="$2"; shift 2 ;;
        --stale-days) [[ $# -ge 2 ]] || usage_error "--stale-days needs an argument"; STALE_DAYS="$2"; shift 2 ;;
        --json) JSON_OUT=true; shift ;;
        -*) usage_error "unknown flag: $1" ;;
        *) usage_error "unexpected argument: $1" ;;
    esac
done

detect_platform() {
    if [[ -n "$PLATFORM" ]]; then echo "$PLATFORM"; return 0; fi
    if [[ -x "${SCRIPT_DIR}/git_platform.sh" ]]; then
        "${SCRIPT_DIR}/git_platform.sh" 2>/dev/null || echo "git"
    else
        echo "git"
    fi
}

# Default fetch: normalize the platform CLI's JSON into our schema.
default_fetch() {
    local platform="$1"
    case "$platform" in
        github)
            command -v gh >/dev/null 2>&1 || { err "gh CLI not found"; return 3; }
            gh pr list --state open --limit 200 \
               --json number,title,author,updatedAt,mergeable,isDraft,headRefName,statusCheckRollup \
               2>/dev/null | python3 -c '
import sys, json
try:
    rows = json.load(sys.stdin)
except Exception:
    print("[]"); sys.exit(0)
def checks(r):
    roll = r.get("statusCheckRollup") or []
    if not roll: return "NONE"
    states = [c.get("conclusion") or c.get("state") or "" for c in roll]
    if any(s in ("FAILURE","ERROR","CANCELLED","TIMED_OUT") for s in states): return "FAIL"
    if any(s in ("PENDING","IN_PROGRESS","QUEUED","") for s in states): return "PENDING"
    return "PASS"
out=[]
for r in rows:
    out.append({
      "number": r.get("number"),
      "title": r.get("title",""),
      "author": (r.get("author") or {}).get("login",""),
      "updated": r.get("updatedAt",""),
      "mergeable": {"MERGEABLE":"CLEAN","CONFLICTING":"CONFLICTING"}.get(r.get("mergeable",""),"UNKNOWN"),
      "checks": checks(r),
      "draft": bool(r.get("isDraft")),
      "head": r.get("headRefName",""),
      "merged": False,
    })
print(json.dumps(out))
' || { err "failed to parse gh output"; return 3; }
            ;;
        gitlab)
            command -v glab >/dev/null 2>&1 || { err "glab CLI not found"; return 3; }
            glab mr list --opened -P 200 -F json 2>/dev/null | python3 -c '
import sys, json
try:
    rows = json.load(sys.stdin)
except Exception:
    print("[]"); sys.exit(0)
out=[]
for r in rows:
    out.append({
      "number": r.get("iid") or r.get("id"),
      "title": r.get("title",""),
      "author": (r.get("author") or {}).get("username",""),
      "updated": r.get("updated_at",""),
      "mergeable": "CLEAN" if r.get("merge_status")=="can_be_merged" else ("CONFLICTING" if r.get("merge_status")=="cannot_be_merged" else "UNKNOWN"),
      "checks": "NONE",
      "draft": bool(r.get("draft") or r.get("work_in_progress")),
      "head": r.get("source_branch",""),
      "merged": False,
    })
print(json.dumps(out))
' || { err "failed to parse glab output"; return 3; }
            ;;
        *)
            err "unsupported platform '$platform' (need a GitHub or GitLab remote)"
            return 2
            ;;
    esac
}

main() {
    local platform; platform="$(detect_platform)"
    local data rc
    if [[ -n "${PR_REVIEW_FETCH:-}" ]]; then
        data="$("$PR_REVIEW_FETCH" "$platform")" || { err "fetch override failed"; exit 2; }
    else
        # Capture the real exit code (a negated `if` would mask it as 0).
        set +e
        data="$(default_fetch "$platform")"; rc=$?
        set -e
        if [[ $rc -ne 0 ]]; then
            [[ $rc -eq 3 ]] && err "cannot enumerate PRs — is the platform CLI installed and authenticated?"
            exit 2
        fi
    fi

    STALE_DAYS="$STALE_DAYS" JSON_OUT="$JSON_OUT" PLATFORM="$platform" \
    python3 -c '
import sys, json, os
from datetime import datetime, timezone
data = json.loads(sys.stdin.read() or "[]")
stale = int(os.environ.get("STALE_DAYS","30"))
json_out = os.environ.get("JSON_OUT")=="true"
platform = os.environ.get("PLATFORM","git")

def age_days(iso):
    if not iso: return 0
    try:
        s = iso.replace("Z","+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except Exception:
        return 0

# supersession: another open PR shares the same head branch
heads={}
for r in data:
    heads.setdefault(r.get("head",""), []).append(r.get("number"))

results=[]
for r in data:
    a = age_days(r.get("updated",""))
    head = r.get("head","")
    superseded = head and len(heads.get(head,[]))>1 and r.get("number")!=min(x for x in heads[head] if x is not None)
    merged = bool(r.get("merged"))
    mergeable = r.get("mergeable","UNKNOWN")
    chk = r.get("checks","NONE")
    draft = bool(r.get("draft"))
    if merged or superseded:
        disp, why = "close", ("branch already merged" if merged else "superseded by an earlier open PR on the same branch")
    elif mergeable=="CONFLICTING" or chk=="FAIL":
        disp, why = "needs-rebase", ("merge conflicts" if mergeable=="CONFLICTING" else "failing checks")
    elif mergeable=="CLEAN" and chk in ("PASS","NONE") and not draft:
        disp, why = "merge", "clean and passing"
    else:
        bits=[]
        if draft: bits.append("draft")
        if a>=stale: bits.append("stale (%dd)"%a)
        if chk=="PENDING": bits.append("checks pending")
        disp, why = "keep", (", ".join(bits) or "active")
    results.append({**r,"age_days":a,"superseded":bool(superseded),"disposition":disp,"rationale":why})

if json_out:
    print(json.dumps(results, indent=2)); sys.exit(0)

print("Open PRs on %s: %d" % (platform, len(results)))
if not results:
    print("Clean queue — no open PRs."); sys.exit(0)
counts={"keep":0,"merge":0,"close":0,"needs-rebase":0}
for r in results:
    counts[r["disposition"]] = counts.get(r["disposition"],0)+1
    print("#%-5s %-50.50s %3dd  %-11s/%-7s -> %s" % (
        r.get("number"), r.get("title",""), r["age_days"],
        r.get("mergeable",""), r.get("checks",""), r["disposition"]))
    print("       rationale: %s" % r["rationale"])
print("Recommended: close %d, merge %d, rebase %d, keep %d" % (
    counts.get("close",0),counts.get("merge",0),counts.get("needs-rebase",0),counts.get("keep",0)))
' <<< "$data"
}

main "$@"
