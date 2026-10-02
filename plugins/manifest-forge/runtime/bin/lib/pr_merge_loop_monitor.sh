# shellcheck shell=bash
# pr_merge_loop_monitor.sh — degraded provider monitor loop for
# pr_merge_loop.sh.
#
# Split out of pr_merge_loop.sh (C-SIZE/CON-002, ceiling 600) along the
# monitor-loop seam, complementing lib/pr_merge_loop_gh.sh's platform-I/O
# layer, lib/pr_merge_loop_fp.sh's observation/state layer, and
# lib/pr_merge_loop_empty_run.sh's counter layer: this file holds only the
# bounded queue-monitoring driver cmd_run falls back to when material
# fingerprinting is unsupported. Sourced, not executed — depends on the
# caller having already defined _now(), err(), cmd_list_managed and
# _managed_numbers, and (via lib/pr_merge_loop_empty_run.sh)
# _monitor_empty_run (see pr_merge_loop.sh).

# cmd_run_monitor — the bounded loop for providers where material
# fingerprinting is unsupported (gitlab today: fp-scope/fp-view/fp-checks/
# fp-threads all refuse via gh_op). Auto-merge is hard-gated bundle-wide and
# per-PR tick handling is impossible without fingerprints, so this loop keeps
# only the OBSERVATION half of the contract: poll the managed queue under the
# same ceiling + 5-empty stop. A non-empty queue is pending work (the
# in-flight analogue — never counted as empty); an empty queue increments the
# consecutive-empty counter exactly like the full path.
cmd_run_monitor() {
    local ceiling="$1" poll="$2"
    local deadline now managed_json managed n
    deadline="$(($(_now) + ceiling))"
    while :; do
        now="$(_now)"
        ((now < deadline)) || break
        managed_json="$(cmd_list_managed)" || return $?
        managed="$(_managed_numbers "$managed_json")" || {
            err "managed-PR observation was malformed"
            return 13
        }
        if [[ -n "$managed" ]]; then
            err "monitor: managed queue pending (${managed}) — auto-merge unsupported on this provider; human action required"
            _monitor_empty_run reset > /dev/null || return $?
        else
            n="$(_monitor_empty_run incr)" || return $?
            if ((n >= 5)); then
                err "5 consecutive empty passes — stopping"
                break
            fi
        fi
        now="$(_now)"
        ((now < deadline)) || break
        [[ "$poll" -gt 0 ]] && sleep "$poll"
    done
    return 0
}
