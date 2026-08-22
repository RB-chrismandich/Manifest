#!/usr/bin/env bash
# loop_lock.sh — per-PR concurrency guard for the auto-dev merge loop (FR-023).
#
# Two layers (research.md R4): a platform LABEL lock (`loop-active`, visible across
# machines/runners) plus a local flock (kills the same-host race cheaply). A label older
# than LOOP_LOCK_STALE_MIN is reclaimable so a crashed run can't wedge a PR forever.
#
# SECURITY (finding 4): the local flock is advisory only — `acquire` is a fresh,
# short-lived subcommand-CLI invocation (not a daemon holding an open descriptor
# across the caller's whole tick), so fd 9 closes and the flock releases the
# instant this process exits, well before the caller finishes the work the lock
# is meant to protect. It cannot provide cross-invocation mutual exclusion; only
# the LABEL lease can, since it is visible to every runner on every host. Each
# lease therefore carries a unique owner token and an expiry ENCODED IN THE LABEL
# NAME ITSELF (`loop-active:<epoch>:<token>`, since GitHub labels have no value
# field), and `acquire` re-reads after adding its lease to break the
# check-then-add race; `release` removes only the lease matching its own token.
#
# Subcommands:
#   acquire <pr>    Take the lock. Exit 0 on success; 1 if genuinely CONTENDED
#                   (a live lease already held by someone else, a lost race, an
#                   inconsistent re-read after our own add, or same-host flock
#                   contention); 2 if the lease could not even be ATTEMPTED
#                   (label_op add itself failed — e.g. the backend rejects an
#                   unprovisioned dynamic label name). 2 is a DEGRADED signal,
#                   not evidence of contention: no one is proven to hold
#                   anything, the attempt just never landed. Callers whose only
#                   remaining use for this lock is avoiding duplicated work
#                   (not guarding anything irreversible) may choose to proceed
#                   on 2 rather than go dark — see pr_merge_loop.sh's cmd_tick.
#   release <pr>    Release the lock (idempotent). Exit 0.
#   is-held <pr>    Exit 0 if held (and not stale), 1 otherwise.
#
# Env: LOOP_LOCK_DIR (local lockfiles), LOOP_LOCK_STALE_MIN (default 15),
#      LOOP_LOCK_LABEL_CMD  seam: "<cmd> has|add|remove <pr> [<owner>]"; `has` prints
#                           "<age-minutes>\t<owner>" for the newest live lease, exit 0
#                           if one exists. Default drives gh via git_ops.sh.

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "loop-lock: $*" >&2; else printf '%s\n' "loop-lock: $*" >&2; fi; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_DIR="${LOOP_LOCK_DIR:-${TMPDIR:-/tmp}/prloop-locks}"
STALE_MIN="${LOOP_LOCK_STALE_MIN:-15}"
LABEL="loop-active"

usage() {
    cat << 'USAGE'
Usage: loop_lock.sh <acquire|release|is-held> <pr>

  acquire <pr>   Take the per-PR lock.
                   0  acquired
                   1  CONTENDED — held by another run (or lost the race)
                   2  DEGRADED — the lease could not be attempted at all
                      (backend rejected the add); not evidence of contention
  release <pr>   Release (idempotent). Exit 0.
  is-held <pr>   Exit 0 if currently held (and not stale), else 1.
USAGE
}

lease_owner_token() {
    local h="${HOSTNAME:-}"
    [[ -n "$h" ]] || h="$(hostname 2> /dev/null || echo host)"
    printf '%s' "$(printf '%s' "$h" | cut -c1-8)-$$-$RANDOM"
}

# Label seam — default implementation drives the platform via git_ops.sh / gh.
# Dynamic label name = "${LABEL}:<epoch>:<owner>" so multiple leases can coexist
# (GitHub labels have no value field; this is how an owner token gets attached
# to the cross-host-visible primitive at all).
label_op() {
    local op="$1" pr="$2" owner="${3:-}"
    if [[ -n "${LOOP_LOCK_LABEL_CMD:-}" ]]; then
        "${LOOP_LOCK_LABEL_CMD}" "$op" "$pr" "$owner"
        return $?
    fi
    case "$op" in
        has)
            local labels line newest_epoch="" newest_owner="" epoch tok
            labels="$("${SCRIPT_DIR}/git_ops.sh" issue-view "$pr" --json labels -q '.labels[].name' 2> /dev/null)" || return 1
            while IFS= read -r line; do
                [[ "$line" == "${LABEL}:"* ]] || continue
                epoch="${line#"${LABEL}:"}"
                epoch="${epoch%%:*}"
                tok="${line#"${LABEL}:${epoch}:"}"
                [[ "$epoch" =~ ^[0-9]+$ ]] || continue
                # Deterministic, order-independent winner: highest epoch, tie-broken
                # by token — every reader of the same lease SET agrees, regardless
                # of the order the platform happens to list labels in.
                if [[ -z "$newest_epoch" || "$epoch" -gt "$newest_epoch" ||
                    ("$epoch" == "$newest_epoch" && "$tok" > "$newest_owner") ]]; then
                    newest_epoch="$epoch"
                    newest_owner="$tok"
                fi
            done <<< "$labels"
            [[ -n "$newest_epoch" ]] || return 1
            local now age
            now="$(date +%s)"
            age=$(((now - newest_epoch) / 60))
            ((age >= 0)) || age=0
            printf '%s\t%s\n' "$age" "$newest_owner"
            return 0
            ;;
        add)
            [[ -n "$owner" ]] || return 1
            # FINDING 1(a) FIX (2026-08-20): a GitHub/GitLab `--add-label` only
            # ATTACHES a label that already exists as a repo label — it never
            # creates one. labels.yml provisions only the static "loop-active"
            # (it cannot provision this name: the epoch+owner suffix is
            # unbounded, generated fresh per acquisition, so no static registry
            # entry could ever cover it). So the dynamic lease name is
            # self-provisioning: create it (idempotently, --force so a retry or
            # a racing runner's identical create is harmless) immediately
            # before attaching it. If creation itself fails (no label-create
            # permission, API error, etc.) the add fails too and the caller
            # sees a DEGRADED acquire (cmd_acquire), not a false success.
            local name
            name="${LABEL}:$(date +%s):${owner}"
            "${SCRIPT_DIR}/git_ops.sh" label-create "$name" \
                --color "FBCA04" \
                --description "Transient per-PR lease for the auto-dev merge loop (auto-created; safe to delete)" \
                --force > /dev/null 2>&1 || return 1
            "${SCRIPT_DIR}/git_ops.sh" issue-edit "$pr" --add-label "$name" > /dev/null 2>&1
            ;;
        remove)
            [[ -n "$owner" ]] || return 0
            local labels line
            labels="$("${SCRIPT_DIR}/git_ops.sh" issue-view "$pr" --json labels -q '.labels[].name' 2> /dev/null)" || return 0
            while IFS= read -r line; do
                [[ "$line" == "${LABEL}:"*":${owner}" ]] || continue
                "${SCRIPT_DIR}/git_ops.sh" issue-edit "$pr" --remove-label "$line" > /dev/null 2>&1
            done <<< "$labels"
            return 0
            ;;
    esac
}

# Prints "<age>\t<owner>" of the active (non-stale) lease, if any; exit 1 if none.
active_lease() {
    local pr="$1" out age owner
    out="$(label_op has "$pr" "")" || return 1
    age="${out%%$'\t'*}"
    owner="${out#*$'\t'}"
    [[ "$age" =~ ^[0-9]+$ ]] || age=0
    ((age <= STALE_MIN)) || return 1 # stale -> treat as free (reclaimable)
    printf '%s\t%s\n' "$age" "$owner"
}

held_active() { active_lease "$1" > /dev/null; }

cmd_acquire() {
    local pr="${1:?pr required}" owner held owner_now
    mkdir -p "$LOCK_DIR" 2> /dev/null || true
    # Same-host, same-instant fast-fail only (see header) — advisory, not the
    # real mutual-exclusion primitive.
    if command -v flock > /dev/null 2>&1; then
        exec 9> "${LOCK_DIR}/${pr}.lock"
        flock -n 9 || {
            err "local lock held for #${pr}"
            return 1
        }
    fi
    if held_active "$pr"; then
        err "#${pr} already locked"
        return 1
    fi
    owner="$(lease_owner_token)"
    # FIX (CDDL QA-critic finding): a failed add must fail the acquire, not be
    # swallowed — silently continuing here would report the lease as taken (exit
    # 0) when it was never written, which is worse than no lock at all: every
    # caller of `acquire` trusts a 0 exit to mean mutual exclusion actually
    # holds. Fail closed instead: no lease on record, no acquire.
    #
    # PROPORTIONALITY FIX (2026-08-20): fail closed does not mean "treat this
    # the same as contention". `held_active` above already answered "is someone
    # else holding it?" from a completely independent read (existing labels on
    # the PR) *before* we ever attempted to add anything — so if we reach this
    # point, no one is known to hold the lease. An `add` failure here means the
    # attempt itself could not land (e.g. label creation failed — no permission,
    # API error, etc.). That is a DEGRADED condition, not evidence of
    # contention, so it gets its own exit code (2) rather than reusing the
    # "held" code (1). A caller for whom this lock only prevents duplicated
    # work (not anything irreversible) can choose to proceed on 2.
    label_op add "$pr" "$owner" || {
        err "#${pr} lease could not be attempted — label backend rejected the add (degraded, NOT evidence of contention)"
        return 2
    }
    # Settle window before the race-break re-read: GitHub labels have no
    # compare-and-swap primitive, so two adds landing within the same instant
    # can each observe an INCOMPLETE lease set if read back immediately (each
    # sees only its own write, both conclude "I won"). This sleep is a
    # best-effort reduction of that window, not a mathematically airtight
    # lock — it trades a small amount of acquire latency (cheap next to the
    # loop's 30s poll cadence) for both readers far more likely to observe the
    # SAME final lease set before deciding a winner.
    sleep "${LOOP_LOCK_SETTLE_SEC:-0.25}"
    # Re-read to break the check-then-add race: GitHub label adds don't reject
    # duplicates, so a competing writer's `add` also "succeeds" — the newest
    # lease on record after both writes is the only one that actually won.
    held="$(active_lease "$pr")" || {
        err "#${pr} lock lost after add"
        return 1
    }
    owner_now="${held#*$'\t'}"
    if [[ "$owner_now" != "$owner" ]]; then
        err "#${pr} lost the race to another runner (owner=${owner_now})"
        label_op remove "$pr" "$owner" || true
        return 1
    fi
    printf '%s' "$owner" > "${LOCK_DIR}/${pr}.owner"
    return 0
}

cmd_release() {
    local pr="${1:?pr required}" owner_file owner=""
    owner_file="${LOCK_DIR}/${pr}.owner"
    [[ -f "$owner_file" ]] && owner="$(cat "$owner_file" 2> /dev/null || true)"
    label_op remove "$pr" "$owner" || true
    rm -f "${LOCK_DIR}/${pr}.lock" "$owner_file" 2> /dev/null || true
    return 0
}
cmd_is_held() { held_active "${1:?pr required}"; }

main() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
        --help | -h | help)
            usage
            exit 0
            ;;
        acquire)
            cmd_acquire "$@"
            exit $?
            ;;
        release)
            cmd_release "$@"
            exit 0
            ;;
        is-held) cmd_is_held "$@" && exit 0 || exit 1 ;;
        *)
            err "unknown subcommand: ${sub:-<none>}"
            usage >&2
            exit 64
            ;;
    esac
}

main "$@"
