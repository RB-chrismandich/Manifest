#!/usr/bin/env bash
# issue_support_hook.sh - PostToolUse dispatcher for the issue-linking hooks.
#
# Reads a PostToolUse payload (JSON) on stdin, inspects the Bash command that
# just ran, and routes to the issue-support engine ONLY when that command
# succeeded:
#   * a PR/MR-creating command  -> issue_support.sh sync-pr
#   * a git commit              -> issue_support.sh sync-commit HEAD
# Never blocks: always exits 0 (PostToolUse must not fail the tool).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="${ISSUE_SUPPORT_ENGINE:-${SCRIPT_DIR}/issue_support.sh}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'USAGE'
Usage: issue_support_hook.sh < <PostToolUse-JSON>

Internal PostToolUse dispatcher. Reads the hook payload on stdin, and on a
successful PR-create / commit command invokes issue_support.sh. Always exits 0.
USAGE
    exit 0
fi

payload="$(cat 2>/dev/null || true)"

# Classify the command and success. Prints "<class>\t<ok>" (class: pr|commit|none).
CLASSIFY_PY='
import sys, json, re
try:
    d = json.load(sys.stdin)
except Exception:
    print("none\t0"); sys.exit(0)
cmd = ((d.get("tool_input") or {}).get("command") or "")
resp = d.get("tool_response")
ok = 1
if isinstance(resp, dict) and (resp.get("is_error") or resp.get("error")):
    ok = 0
low = cmd.lower()
cl = "none"
# Anchor on an actual CLI invocation (gh/glab/git/git_ops.sh) so that unrelated
# commands containing "pr-create" or "git ... commit" as substrings do not fire.
if re.search(r"^\s*(sudo\s+)?(\S*/)?(gh|glab|\S*git_ops\.sh)\s+(pr|mr)[ -]create\b", low):
    cl = "pr"
elif re.search(r"^\s*(sudo\s+)?(\S*/)?(\S*git_ops\.sh\s+commit|git\s+commit)\b", low):
    cl = "commit"
print("%s\t%s" % (cl, ok))
'

result="$(printf '%s' "${payload}" | python3 -c "${CLASSIFY_PY}" 2>/dev/null || printf 'none\t0')"
cls="${result%%	*}"
ok="${result##*	}"

if [[ "${ok}" != "1" ]]; then
    exit 0   # the underlying command failed (H4) — do not sync
fi

case "${cls}" in
    pr)     "${ENGINE}" sync-pr     >&2 2>&1 || true ;;
    commit) "${ENGINE}" sync-commit HEAD >&2 2>&1 || true ;;
    *)      : ;;
esac

exit 0
