#!/usr/bin/env bash
# loop_lock.sh — per-PR concurrency guard for the auto-dev merge loop (FR-023).
#
# Two layers (research.md R4): a platform LABEL lock (`loop-active`, visible across
# machines/runners) plus a local flock (kills the same-host race cheaply). A label older
# than LOOP_LOCK_STALE_MIN is reclaimable so a crashed run can't wedge a PR forever.
#
# Subcommands:
#   acquire <pr>    Take the lock. Exit 0 on success, 1 if already held (and not stale).
#   release <pr>    Release the lock (idempotent). Exit 0.
#   is-held <pr>    Exit 0 if held (and not stale), 1 otherwise.
#
# Env: LOOP_LOCK_DIR (local lockfiles), LOOP_LOCK_STALE_MIN (default 15),
#      LOOP_LOCK_LABEL_CMD  seam: "<cmd> has|add|remove <pr>"; `has` prints age-minutes,
#                           exit 0 if held. Default drives gh via git_ops.sh.

set -euo pipefail

err() { echo "loop-lock: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_DIR="${LOOP_LOCK_DIR:-${TMPDIR:-/tmp}/prloop-locks}"
STALE_MIN="${LOOP_LOCK_STALE_MIN:-15}"
LABEL="loop-active"

usage() {
    cat <<'USAGE'
Usage: loop_lock.sh <acquire|release|is-held> <pr>

  acquire <pr>   Take the per-PR lock. Exit 0 ok, 1 if held by another run.
  release <pr>   Release (idempotent). Exit 0.
  is-held <pr>   Exit 0 if currently held (and not stale), else 1.
USAGE
}

# Label seam — default implementation drives the platform via git_ops.sh / gh.
label_op() {
    local op="$1" pr="$2"
    if [[ -n "${LOOP_LOCK_LABEL_CMD:-}" ]]; then
        "${LOOP_LOCK_LABEL_CMD}" "$op" "$pr"; return $?
    fi
    case "$op" in
        has)    "${SCRIPT_DIR}/git_ops.sh" issue-view "$pr" --json labels 2>/dev/null \
                  | grep -q "\"${LABEL}\"" && { echo 0; return 0; } || return 1 ;;
        add)    "${SCRIPT_DIR}/git_ops.sh" issue-edit "$pr" --add-label "${LABEL}" >/dev/null 2>&1 ;;
        remove) "${SCRIPT_DIR}/git_ops.sh" issue-edit "$pr" --remove-label "${LABEL}" >/dev/null 2>&1 ;;
    esac
}

# Held (and not stale)? prints nothing; exit 0 if effectively held.
held_active() {
    local pr="$1" age=0
    age="$(label_op has "$pr")" || return 1     # not held at all
    [[ "${age:-0}" =~ ^[0-9]+$ ]] || age=0
    (( age <= STALE_MIN ))                       # stale → treat as free (reclaimable)
}

cmd_acquire() {
    local pr="${1:?pr required}"
    mkdir -p "$LOCK_DIR" 2>/dev/null || true
    # Same-host guard (best-effort; absent flock degrades to the label lock alone).
    if command -v flock >/dev/null 2>&1; then
        exec 9>"${LOCK_DIR}/${pr}.lock"
        flock -n 9 || { err "local lock held for #${pr}"; return 1; }
    fi
    if held_active "$pr"; then err "#${pr} already locked"; return 1; fi
    label_op add "$pr" || true
    # Re-read to break the check-then-set race; a competing writer means both back off.
    if ! held_active "$pr"; then err "#${pr} lock lost after add"; return 1; fi
    return 0
}

cmd_release() { label_op remove "${1:?pr required}" || true; rm -f "${LOCK_DIR}/${1}.lock" 2>/dev/null || true; return 0; }
cmd_is_held() { held_active "${1:?pr required}"; }

main() {
    local sub="${1:-}"; shift || true
    case "${sub}" in
        --help|-h|help) usage; exit 0 ;;
        acquire)        cmd_acquire "$@"; exit $? ;;
        release)        cmd_release "$@"; exit 0 ;;
        is-held)        cmd_is_held "$@" && exit 0 || exit 1 ;;
        *) err "unknown subcommand: ${sub:-<none>}"; usage >&2; exit 64 ;;
    esac
}

main "$@"
