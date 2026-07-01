#!/usr/bin/env bash
# verification_gate.sh — post-implementation verification gate for /auto-issue-dev (#360).
#
# Reuses the existing parallel_agent.py consensus engine as a CONSUMER (it does not modify
# it). Tier-1 findings block a real PR (→ draft + needs-human); Tier-2 and the consensus
# score are advisory for PR-open. Split into a non-deterministic `review` and a pure,
# offline-testable `decide` so the safety logic is unit-tested (tests/bats/verification_gate.bats).
# Design: docs/superpowers/specs/2026-06-18-auto-issue-dev-verification-gate-design.md
#
# Subcommands:
#   review <issue>     Build+redact a review packet, run the reviewer behind an injectable
#                      seam, emit gate JSON {tier1,tier2,consensus_score,verdict,reviewer_error}.
#   decide [<gate>]    Pure core: map gate JSON (arg/stdin) to {action,label,annotation,reason}.
#
# Env: VERIFICATION_GATE_REVIEW_CMD  reviewer seam (default: parallel_agent.py --json --validate --review)
#      VERIFICATION_GATE_HIGH/LOW    consensus thresholds (default 0.80 / 0.50)

set -euo pipefail

err() { echo "verification-gate: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HIGH="${VERIFICATION_GATE_HIGH:-0.80}"
LOW="${VERIFICATION_GATE_LOW:-0.50}"

usage() {
    cat << 'USAGE'
Usage: verification_gate.sh <review <issue> | decide [<gate-json>]>

  review <issue>   Run the gate reviewer (behind VERIFICATION_GATE_REVIEW_CMD seam);
                   emit gate JSON. Reviewer failure -> reviewer_error sentinel (fail closed).
  decide [<gate>]  Map gate JSON to {action,label,annotation,reason}. Always exits 0.
USAGE
}

DECIDE_PY='
import json, sys, os
HIGH=float(os.environ.get("VG_HIGH","0.80")); LOW=float(os.environ.get("VG_LOW","0.50"))
raw=sys.argv[1] if len(sys.argv)>1 and sys.argv[1]!="" else sys.stdin.read()
def out(a,label,ann,reason):
    print(json.dumps({"action":a,"label":label,"annotation":ann,"reason":reason,
        "tier1_passed":(a=="pr-open"),"consensus":g_consensus}));sys.exit(0)
try: d=json.loads(raw)
except Exception:
    g_consensus=0.0; out("draft-needs-human","needs-human","verification gate output unparseable","fail closed")
try: g_consensus=float(d.get("consensus_score",0) or 0)
except Exception: g_consensus=0.0
if d.get("reviewer_error") is True:
    out("draft-needs-human","needs-human","verification gate could not run","reviewer infrastructure failure")
t1=d.get("tier1",{}) or {}
if t1.get("passed") is not True:
    issues=t1.get("issues") or []
    out("draft-needs-human","needs-human","Tier-1 findings: %s"%(", ".join(map(str,issues)) or "unspecified"),"tier1 blocked")
t2=d.get("tier2",{}) or {}; concerns=t2.get("concerns") or []
note="Tier-2 advisory: %s"%(", ".join(map(str,concerns)) or "none")
if g_consensus>=HIGH:
    out("pr-open",None,note,"tier1 pass, consensus high")
out("pr-open",None,"⚠ reviewer disagreement (consensus %.2f); %s"%(g_consensus,note),"tier1 pass, consensus advisory")
'

cmd_decide() { VG_HIGH="$HIGH" VG_LOW="$LOW" python3 -c "${DECIDE_PY}" "${1:-}"; }

cmd_review() {
    local issue="${1:-}"
    [[ -n "$issue" ]] || {
        err "review: issue number required"
        return 64
    }
    local packet
    packet="$(mktemp "${TMPDIR:-/tmp}/vgate-packet.XXXXXX")"
    # shellcheck disable=SC2064
    trap "rm -f '$packet'" RETURN

    # Best-effort packet: acceptance criteria + branch diff (errors tolerated — the reviewer
    # still gets whatever context is available; a thin packet is not a safety failure).
    {
        echo "# Review packet for issue #${issue}"
        "${SCRIPT_DIR}/git_ops.sh" issue-view "$issue" 2> /dev/null || true
        echo "---DIFF---"
        # The number under review is a PR in the merge loop — its diff lives on the platform,
        # not in the caller's checkout (which may be a different branch entirely). Fall back to
        # the local branch diff for pre-PR (issue-flow) callers.
        "${SCRIPT_DIR}/git_ops.sh" pr-diff "$issue" 2> /dev/null ||
            git diff "origin/main...HEAD" 2> /dev/null || git diff 2> /dev/null || true
    } > "$packet" 2> /dev/null || true

    # Redact before the packet leaves the process.
    if [[ -x "${SCRIPT_DIR}/audit_log.sh" ]]; then
        "${SCRIPT_DIR}/audit_log.sh" redact "$(cat "$packet")" > "${packet}.r" 2> /dev/null &&
            mv "${packet}.r" "$packet" || true
    fi

    local cmd raw rc=0
    # --timeout 600: the 120s parallel_agent default is documented as insufficient for a
    # multi-agent diff review (CLAUDE.md orchestration guide) and was producing reviewer_error.
    cmd="${VERIFICATION_GATE_REVIEW_CMD:-${SCRIPT_DIR}/parallel_agent.py --json --validate --timeout 600 --review}"
    raw="$(eval "${cmd} \"${packet}\"" 2> /dev/null)" || rc=$?

    # Adapt to gate JSON. parallel_agent emits {validation:{tier1,tier2,verdict},
    # cross_verification:{consensus_score}}; a seam may already emit gate-shaped JSON
    # (top-level tier1) — pass that through. Anything else fails closed.
    local shaped=""
    if [[ $rc -eq 0 ]]; then
        shaped="$(printf '%s' "$raw" | python3 -c '
import json, sys
try: d = json.load(sys.stdin)
except Exception: sys.exit(1)
if isinstance(d.get("tier1"), dict):
    print(json.dumps(d)); sys.exit(0)
v = d.get("validation")
if isinstance(v, dict) and isinstance(v.get("tier1"), dict):
    # Consensus for merge_decision must be a FRACTION (banded at 0.80). The tier1
    # cross_verification check carries it as one; cross_verification.consensus_score is
    # PERCENT-scale (log prints "Consensus score: N%") — normalize, never pass raw.
    cons = ((v["tier1"].get("checks") or {}).get("cross_verification") or {}).get("score")
    if cons is None:
        cons = (d.get("cross_verification") or {}).get("consensus_score", 0) / 100.0
    print(json.dumps({"tier1": v["tier1"], "tier2": v.get("tier2") or {},
        "consensus_score": cons,
        "verdict": v.get("verdict", "UNKNOWN")})); sys.exit(0)
sys.exit(1)' 2> /dev/null)" || shaped=""
    fi
    if [[ -z "$shaped" ]]; then
        printf '%s\n' '{"reviewer_error":true,"tier1":{"passed":false},"consensus_score":0,"verdict":"BLOCKED"}'
        return 0
    fi
    printf '%s\n' "$shaped"
}

main() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
        --help | -h | help)
            usage
            exit 0
            ;;
        review)
            cmd_review "$@"
            exit $?
            ;;
        decide)
            cmd_decide "$@"
            exit 0
            ;;
        *)
            err "unknown subcommand: ${sub:-<none>}"
            usage >&2
            exit 64
            ;;
    esac
}

main "$@"
