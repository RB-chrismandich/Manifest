# shellcheck shell=bash
# Static user-facing usage text for pr_merge_loop.sh.

usage() {
    cat << 'USAGE'
Usage: pr_merge_loop.sh <subcommand> [args]

  list-managed [--json]        Automation-authored open PRs (skips humans).
  signals <pr> [--json]        Recompute merge_decision input JSON for a PR.
  empty-run <get|incr|reset>   Consecutive-empty-run counter (stops loop at 5).
  address-status <pr>          Observe once; report actionable or blocked on human.
  record-human-blocked <pr>    Persist an established human-only disposition.
  set-disposition <pr> <v>     Record the /pr-review verdict (merge|keep|close) for signals.
  merge <pr>                   HARD-GATED in this bundle: always refuses, exit 78.
  tick <pr>                    Decide + dispatch one PR (lock, run-gate, act).
  run [--apply]                Self-paced bounded loop (10-min ceiling; stop at 5 empty).
  post-merge-check             main HEAD CI health (exit 10 on red).
USAGE
}
