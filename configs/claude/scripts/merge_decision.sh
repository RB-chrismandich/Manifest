#!/usr/bin/env bash
# merge_decision.sh — pure, deterministic merge-decision core for the auto-dev merge loop.
#
# No network, no gh, no filesystem writes: maps a recomputed signals JSON to an action.
# This isolation is deliberate — the merge is the only irreversible action in the loop, so
# its decision logic must be unit-testable offline (see tests/bats/merge_decision.bats and
# specs/361-auto-dev-merge-loop/contracts/merge_decision.md).
#
# Subcommands:
#   decide [<signals-json>]   Read signals (arg or stdin), print {action,reason,label} JSON.
#
# Always exits 0 — the decision is the payload. Malformed input fails closed (hand-human).

set -euo pipefail

err() { echo "merge-decision: $*" >&2; }

usage() {
    cat <<'USAGE'
Usage: merge_decision.sh decide [<signals-json>]

  decide   Map a signals JSON (arg or stdin) to {action, reason, label}.
           action ∈ merge|revise|wait|update-branch|hand-human|halt
           Always exits 0; malformed input fails closed (hand-human).
USAGE
}

DECIDE_PY='
import json, sys

raw = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "" else sys.stdin.read()
def out(action, reason, label=None):
    print(json.dumps({"action": action, "reason": reason, "label": label}))
    sys.exit(0)

try:
    s = json.loads(raw)
except Exception:
    out("hand-human", "unparseable signals — failing closed", "needs-human")

g = lambda k, d=None: s.get(k, d)
checks   = g("checks", "PENDING")
verify   = g("verify", "pass")
mstate   = g("merge_state", "UNKNOWN")
mergeable= g("mergeable", "UNKNOWN")
disp     = g("pr_review_disposition", "keep")
try:    consensus = float(g("consensus", 0) or 0)
except Exception: consensus = 0.0
try:    rev = int(g("revisions_used", 0) or 0)
except Exception: rev = 0
try:    maxrev = int(g("max_revisions", 3) or 3)
except Exception: maxrev = 3

# Fail-closed ordering — first match wins.
if g("main_ci") == "red":
    out("halt", "main CI went red after a merge — stop the line", None)
if g("reviewer_error") is True or g("gate_tier1") == "fail":
    out("hand-human", "verification gate could not run or Tier-1 failed", "needs-human")
if g("hold") is True or g("review_block") is True:
    out("hand-human", "human request-changes / hold present", "needs-human")
if mergeable == "CONFLICTING" or mstate == "DIRTY":
    out("hand-human", "merge conflict with base", "needs-human")
if mstate == "BEHIND":
    out("update-branch", "head behind base — update once", None)

revisable = (checks == "FAIL") or (verify == "fail-blocking")
if revisable:
    if rev < maxrev:
        out("revise", "failing checks/verify with revision budget remaining", None)
    out("hand-human", "revision budget exhausted, still not clear", "needs-human")

if checks == "PENDING" or mergeable == "UNKNOWN" or mstate in ("UNSTABLE", "UNKNOWN"):
    out("wait", "checks/mergeability still settling — re-poll", None)
if checks == "NO_CHECKS":
    out("hand-human", "no CI configured — refusing to auto-merge un-verified code", "needs-human")

clear = (checks == "PASS" and g("review_block") is not True and disp == "merge"
         and verify == "pass" and g("gate_tier1") == "pass"
         and mstate in ("CLEAN", "HAS_HOOKS") and g("hold") is not True
         and mergeable == "MERGEABLE")
if not clear:
    if rev < maxrev:
        out("revise", "not yet clear (e.g. pr-review not merge) — another cycle", None)
    out("hand-human", "not clear and out of revisions", "needs-human")

# All clear — consensus decides (Constitution III banding; merge gate blocks <0.80).
if consensus >= 0.80:
    out("merge", "all clear and consensus high", None)
if consensus >= 0.50:
    out("hand-human", "all clear but consensus mid — needs a human", "ready-to-merge")
out("hand-human", "all clear but consensus low — block + synthesize", "needs-human")
'

cmd_decide() { python3 -c "${DECIDE_PY}" "${1:-}"; }

main() {
    local sub="${1:-}"; shift || true
    case "${sub}" in
        --help|-h|help) usage; exit 0 ;;
        decide)         cmd_decide "$@"; exit 0 ;;
        *) err "unknown subcommand: ${sub:-<none>}"; usage >&2; exit 64 ;;
    esac
}

main "$@"
