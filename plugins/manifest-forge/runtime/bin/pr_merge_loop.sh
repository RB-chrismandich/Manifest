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
# shellcheck disable=SC2034  # consumed by the sourced lib/pr_merge_loop_fp.sh
STATE_DIR="${PR_MERGE_LOOP_STATE_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/manifest/forge/pr_merge_loop}"
# shellcheck disable=SC2034  # consumed by the sourced lib/pr_merge_loop_fp.sh
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

# --- observation & transition-state layer: split out of this file into
# lib/pr_merge_loop_fp.sh (C-SIZE/CON-002 — see that file's header for the
# seam rationale). Provides cmd_signals, cmd_list_managed, cmd_empty_run,
# cmd_address_cycle, cmd_set_disposition, cmd_post_merge_check, _jget, and the
# collect_fingerprint_material / fingerprint_state_* machinery.
# shellcheck source=lib/pr_merge_loop_fp.sh disable=SC1091
source "${SCRIPT_DIR}/lib/pr_merge_loop_fp.sh"

# --- merge path (T019) + dispatch (T021) ---
APPLY="${PR_MERGE_LOOP_APPLY:-0}"

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
        # Only genuine reviewer/infra failure degrades the run without persisting state.
        # A valid gate verdict (even BLOCKED / Tier-1 fail) is a completed observation
        # and must persist its fingerprint to prevent infinite review loops.
        if [[ "$(printf '%s' "$sig2" | _jget reviewer_error 2> /dev/null)" == "True" ]]; then
            handling_failed=1
        fi
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
