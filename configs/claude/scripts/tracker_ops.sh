#!/usr/bin/env bash
# tracker_ops.sh - Provider-agnostic issue-tracker operations dispatcher.
# Engines: git_ops.sh (github/gitlab), linear_ops.sh (linear); jira is MCP-only.
# Registry: configs/claude/config/tracker_providers.yml (via tracker_registry.py).

set -euo pipefail

usage() {
    cat << 'USAGE'
Usage: tracker_ops.sh [--provider github|gitlab|linear|jira] <verb> [args...]
Verbs: resolve-provider | issue-list | issue-view N | issue-create |
       issue-comment N TEXT | issue-transition N CANONICAL_STATUS |
       issue-label N --add-label L [--remove-label L] | issue-close N |
       duplicate-mark N --duplicate-of M | sub-issue-create | sub-issue-list N
Detection: --provider > MANIFEST_TRACKER > .manifest-tracker file >
           git remote (github/gitlab) > registry default_provider.
Exit codes: 3 = provider is MCP-only in shell context; 4 = verb not
implemented for provider (both mean: skip loudly, do not fail silently).
USAGE
}
[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && { usage; exit 0; }

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "tracker-ops: $*" >&2; else printf '%s\n' "tracker-ops: $*" >&2; fi; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${SCRIPT_DIR}/tracker_registry.py"
# shellcheck disable=SC2034 # Used in Task 4 verb dispatch
GIT_OPS="${SCRIPT_DIR}/git_ops.sh"
# shellcheck disable=SC2034
LINEAR_OPS="${SCRIPT_DIR}/linear_ops.sh"

valid_provider() { case "$1" in github | gitlab | linear | jira) return 0 ;; *) return 1 ;; esac; }

resolve_provider() {
    local p=""
    if [[ -n "${FORCED_PROVIDER:-}" ]]; then p="${FORCED_PROVIDER}"
    elif [[ -n "${MANIFEST_TRACKER:-}" ]]; then p="${MANIFEST_TRACKER}"
    else
        local root
        root=$(git rev-parse --show-toplevel 2> /dev/null || true)
        if [[ -n "${root}" && -f "${root}/.manifest-tracker" ]]; then
            p=$(tr -d '[:space:]' < "${root}/.manifest-tracker")
        else
            local plat
            plat=$(bash "${SCRIPT_DIR}/git_platform.sh" 2> /dev/null || echo git)
            case "${plat}" in
                github | gitlab) p="${plat}" ;;
                *) p=$(python3 "${REGISTRY}" default-provider) ;;
            esac
        fi
    fi
    if ! valid_provider "${p}"; then
        err "invalid provider: ${p} (valid: github gitlab linear jira)"
        return 1
    fi
    echo "${p}"
}

FORCED_PROVIDER=""
if [[ "${1:-}" == "--provider" ]]; then
    FORCED_PROVIDER="$2"
    shift 2
fi
[[ $# -eq 0 ]] && { usage >&2; exit 1; }
verb="$1"
shift

provider=$(resolve_provider) || exit 1

case "${verb}" in
    resolve-provider)
        echo "${provider}"
        exit 0
        ;;
    *)
        err "Unknown verb: ${verb}"
        usage >&2
        exit 1
        ;;
esac
