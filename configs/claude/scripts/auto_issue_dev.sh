#!/usr/bin/env bash
# auto_issue_dev.sh - selection/dependency/flagging engine for /auto-issue-dev
#
# Wraps git_ops.sh. Picks the next opted-in ('auto-dev') issue that is ready to
# develop, skipping (and tagging) ones with unmet dependencies. Failure/dependency
# flagging is fail-open.
#
# Subcommands:
#   next-issue [--json]        First READY auto-dev issue; exit 3 when none
#   check-deps <N> [--json]    Exit 2 if issue N has unmet dependency refs
#   mark-blocked <N> <reason>  Add needs-human label + deduped comment (exit 0)
#   mark-dependency <N> <refs> Add blocked-dependency label + deduped comment (exit 0)
#
# Env seams: GIT_OPS_BIN, GIT_PLATFORM_BIN, AUTO_ISSUE_DEV_LABEL,
#            AUTO_ISSUE_DEV_DEP_LABEL, AUTO_ISSUE_DEV_FAIL_LABEL

set -euo pipefail

err() { echo "auto-issue-dev: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_OPS_BIN="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
GIT_PLATFORM_BIN="${GIT_PLATFORM_BIN:-${SCRIPT_DIR}/git_platform.sh}"
DEV_LABEL="${AUTO_ISSUE_DEV_LABEL:-auto-dev}"
DEP_LABEL="${AUTO_ISSUE_DEV_DEP_LABEL:-blocked-dependency}"
FAIL_LABEL="${AUTO_ISSUE_DEV_FAIL_LABEL:-needs-human}"

git_ops() { "${GIT_OPS_BIN}" "$@"; }

usage() {
    cat <<'USAGE'
Usage: auto_issue_dev.sh <subcommand> [args]

  next-issue [--json]          First READY auto-dev issue; exit 3 when none
  check-deps <N> [--json]      Exit 2 if issue N has unmet dependency refs
  mark-blocked <N> <reason>    Add needs-human label + deduped comment
  mark-dependency <N> <refs>   Add blocked-dependency label + deduped comment

Fail-open: mark-* always exit 0. Opt-in label: auto-dev.
USAGE
}

main() {
    local sub="${1:-}"; shift || true
    case "${sub}" in
        --help|-h|help) usage; exit 0 ;;
        *) err "unknown subcommand: ${sub:-<none>}"; usage >&2; exit 64 ;;
    esac
}

main "$@"
