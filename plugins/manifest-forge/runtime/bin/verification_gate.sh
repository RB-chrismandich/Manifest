#!/usr/bin/env bash
# verification_gate.sh — post-implementation verification gate for /issue-dev-auto (#360).
#
# Runs one injected reviewer behind a fail-closed schema boundary. Tier-1
# findings block a real PR (→ draft + needs-human); Tier-2 evidence is advisory
# for PR-open. Split into a non-deterministic `review` and a pure, offline-
# testable `decide` so the safety logic is unit-tested.
#
# Subcommands:
#   review <issue>     Build+redact a review packet, run the reviewer behind an injectable
#                      seam, emit gate JSON {tier1,tier2,verdict,reviewer_error}.
#   decide [<gate>]    Pure core: map gate JSON (arg/stdin) to {action,label,annotation,reason}.
#
# Env: VERIFICATION_GATE_REVIEW_CMD  required reviewer seam.

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "verification-gate: $*" >&2; else printf '%s\n' "verification-gate: $*" >&2; fi; }

# The `manifest` CLI lives in ~/.local/bin, which a login shell gets from the
# user's profile but hooks, launchd/systemd jobs and cron do not. Put it back on
# PATH rather than hardcoding the path: the command seams below are word-split
# strings, so an absolute path would break on a $HOME containing spaces.
# ${HOME:-} because a clean env (env -i, some CI/hook contexts) has no HOME and
# these scripts run under `set -u` — the --help path must not need it.
case ":${PATH:-}:" in
    *":${HOME:-}/.local/bin:"*) ;;
    *) [[ -n "${HOME:-}" ]] && PATH="$HOME/.local/bin:${PATH:-}" ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat << 'USAGE'
Usage: verification_gate.sh <review <issue> | decide [<gate-json>]>

  review <issue>   Run the gate reviewer (behind VERIFICATION_GATE_REVIEW_CMD seam);
                   emit gate JSON. Reviewer failure -> reviewer_error sentinel (fail closed).
  decide [<gate>]  Map gate JSON to {action,label,annotation,reason}. Always exits 0.
USAGE
}

DECIDE_PY='
import json, sys
raw=sys.argv[1] if len(sys.argv)>1 and sys.argv[1]!="" else sys.stdin.read()
def out(a,label,ann,reason):
    print(json.dumps({"action":a,"label":label,"annotation":ann,"reason":reason,
        "tier1_passed":(a=="pr-open")}));sys.exit(0)
try:
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise TypeError("top-level payload must be a JSON object")
except Exception:
    out("draft-needs-human", "needs-human", "verification gate output unparseable", "fail closed")
if d.get("reviewer_error") is True:
    out("draft-needs-human", "needs-human", "verification gate could not run", "reviewer infrastructure failure")
t1 = d.get("tier1")
if not isinstance(t1, dict) or t1.get("passed") is not True:
    raw_issues = t1.get("issues") if isinstance(t1, dict) else []
    issues = [str(x) for x in raw_issues] if isinstance(raw_issues, list) else ([str(raw_issues)] if raw_issues else [])
    out("draft-needs-human", "needs-human", "Tier-1 findings: %s" % (", ".join(issues) or "unspecified"), "tier1 blocked")
t2 = d.get("tier2")
raw_concerns = t2.get("concerns") if isinstance(t2, dict) else []
concerns = [str(x) for x in raw_concerns] if isinstance(raw_concerns, list) else ([str(raw_concerns)] if raw_concerns else [])
note = "Tier-2 advisory: %s" % (", ".join(concerns) or "none")
out("pr-open", None, note, "tier1 evidence clear")
'

cmd_decide() { python3 -c "${DECIDE_PY}" "${1:-}"; }

cmd_review() {
    local issue="${1:-}"
    [[ -n "$issue" ]] || {
        err "review: issue number required"
        return 64
    }
    local packet platform
    packet="$(mktemp "${TMPDIR:-/tmp}/vgate-packet.XXXXXX")"
    platform="$(bash "${SCRIPT_DIR}/git_platform.sh" 2> /dev/null || printf git)"
    # shellcheck disable=SC2064
    trap "rm -f '$packet'" RETURN

    # Best-effort packet: acceptance criteria + branch diff (errors tolerated — the reviewer
    # still gets whatever context is available; a thin packet is not a safety failure).
    {
        echo "# Review packet for issue #${issue}"
        case "${platform}" in
            github) gh issue view "$issue" 2> /dev/null || true ;;
            gitlab) glab issue view "$issue" 2> /dev/null || true ;;
            *) : ;;
        esac
        echo "---DIFF---"
        case "${platform}" in
            github) gh pr diff "$issue" 2> /dev/null || git diff "origin/main...HEAD" 2> /dev/null || git diff 2> /dev/null || true ;;
            gitlab) glab mr diff "$issue" 2> /dev/null || git diff "origin/main...HEAD" 2> /dev/null || git diff 2> /dev/null || true ;;
            *) git diff "origin/main...HEAD" 2> /dev/null || git diff 2> /dev/null || true ;;
        esac
    } > "$packet" 2> /dev/null || true

    # Redact before the packet leaves the process.
    #
    # Two defects fixed here (2026-08-22, Codex + Cursor both HIGH):
    #  1. `redact "$(cat "$packet")"` passed the whole packet as one ARGV
    #     element. A multi-megabyte PR diff exceeds ARG_MAX, exec fails, and
    #     nothing is redacted. Feed it on stdin instead -- no size ceiling.
    #  2. The trailing `|| true` then let execution continue with the ORIGINAL
    #     unredacted packet, which was handed straight to the configured
    #     reviewer. Any secret in that raw diff left the process. Redaction is
    #     a security control, so its failure must fail the gate, not be
    #     swallowed: fall through to reviewer_error/BLOCKED instead.
    if [[ -x "${SCRIPT_DIR}/audit_log.sh" ]]; then
        if "${SCRIPT_DIR}/audit_log.sh" redact < "$packet" > "${packet}.r" 2> /dev/null &&
            [[ -s "${packet}.r" || ! -s "$packet" ]]; then
            mv "${packet}.r" "$packet"
        else
            rm -f "${packet}.r"
            err "redaction failed — refusing to send an unredacted review packet"
            printf '%s\n' '{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED","reviewer_error":true}'
            return 0
        fi
    fi

    local raw="" rc=0 shaped=""
    local cmd_str="${VERIFICATION_GATE_REVIEW_CMD:-}"
    if [[ -n "$cmd_str" ]]; then
        local -a cmd_arr
        read -r -a cmd_arr <<< "$cmd_str"
        raw="$("${cmd_arr[@]}" "$packet" 2> /dev/null)" || rc=$?
    else
        rc=127
    fi

    # Only the injected gate schema crosses this boundary. Incomplete results
    # and failed Tier-1 checks are indistinguishable from a reviewer failure and
    # fail closed.
    if [[ $rc -eq 0 ]]; then
        shaped="$(printf '%s' "$raw" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    required = {"tier1", "tier2", "verdict"}
    allowed = required | {"reviewer_error", "consensus_score"}
    valid = (
        isinstance(d, dict)
        and required <= set(d)
        and set(d) <= allowed
        and isinstance(d["tier1"], dict) and set(d["tier1"]) == {"passed"}
        and isinstance(d["tier1"]["passed"], bool)
        and isinstance(d["tier2"], dict) and set(d["tier2"]) == {"concerns"}
        and isinstance(d["tier2"]["concerns"], list)
        and isinstance(d["verdict"], str)
        and ("reviewer_error" not in d or isinstance(d["reviewer_error"], bool))
    )
    if not valid:
        raise ValueError("invalid gate schema")
    print(json.dumps(d))
except Exception:
    sys.exit(1)' 2> /dev/null)" || shaped=""
    fi
    if [[ -z "$shaped" ]]; then
        printf '%s\n' '{"tier1":{"passed":false},"tier2":{"concerns":[]},"verdict":"BLOCKED","reviewer_error":true}'
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
