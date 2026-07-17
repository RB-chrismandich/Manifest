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
GIT_OPS="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
LINEAR_OPS="${LINEAR_OPS_BIN:-${SCRIPT_DIR}/linear_ops.sh}"
CANONICAL_STATUSES=(planned in-progress needs-review "done")

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

if [[ "${provider}" == "jira" ]]; then
    if [[ "${verb}" == "resolve-provider" ]]; then echo jira; exit 0; fi
    err "unsupported-in-context: jira access is MCP-only; run from agent context"
    err "(registry: tracker_providers.yml providers.jira.access)"
    exit 3
fi

engine() { # route a verb 1:1 to the provider engine
    case "${provider}" in
        github | gitlab) bash "${GIT_OPS}" "$@" ;;
        linear) bash "${LINEAR_OPS}" "$@" ;;
    esac
}

status_name() { python3 "${REGISTRY}" status "${provider}" "$1"; }

case "${verb}" in
    resolve-provider) echo "${provider}" ;;
    issue-list | issue-view | issue-create | issue-comment | issue-close)
        engine "${verb}" "$@"
        ;;
    issue-label)
        case "${provider}" in
            github | gitlab) engine issue-edit "$@" ;;
            linear)
                # linear_ops.sh issue-update only supports --state/--priority;
                # it has no label-mutation to route --add-label/--remove-label
                # to (registry: tracker_providers.yml — labels are status-
                # transition-only on linear via issue-transition).
                err "issue-label not implemented for linear (registry documents the mapping; see spec §4.1)"
                exit 4
                ;;
        esac
        ;;
    issue-transition)
        n="${1:-}" target="${2:-}"
        [[ -n "${n}" && -n "${target}" ]] || { err "usage: issue-transition N CANONICAL_STATUS"; exit 1; }
        case "${provider}" in
            github | gitlab)
                args=("${n}")
                for s in "${CANONICAL_STATUSES[@]}"; do
                    [[ "${s}" != "${target}" ]] && args+=(--remove-label "${s}")
                done
                args+=(--add-label "$(status_name "${target}")")
                engine issue-edit "${args[@]}"
                ;;
            linear)
                engine transition-state --identifier "${n}" --state "$(status_name "${target}")"
                ;;
        esac
        ;;
    duplicate-mark)
        n="${1:-}"
        [[ -n "${n}" ]] || { err "usage: duplicate-mark N --duplicate-of M"; exit 1; }
        shift
        [[ "${1:-}" == "--duplicate-of" ]] || { err "usage: duplicate-mark N --duplicate-of M"; exit 1; }
        primary="${2:-}"
        [[ -n "${primary}" ]] || { err "usage: duplicate-mark N --duplicate-of M"; exit 1; }
        case "${provider}" in
            linear) engine issue-mark-duplicate "${n}" --duplicate-of "${primary}" ;;
            github | gitlab)
                engine issue-comment "${n}" "Duplicate of #${primary}"
                engine issue-edit "${n}" --add-label duplicate
                engine issue-close "${n}"
                ;;
        esac
        ;;
    sub-issue-create | sub-issue-list)
        case "${provider}" in
            linear)
                if [[ "${verb}" == "sub-issue-create" ]]; then
                    engine create-sub-issue "$@"
                else
                    engine list-sub-issues "$@"
                fi
                ;;
            github | gitlab)
                err "${verb} not implemented for ${provider} (registry documents the mapping; see spec §4.1)"
                exit 4
                ;;
        esac
        ;;
    *)
        err "Unknown verb: ${verb}"
        usage >&2
        exit 1
        ;;
esac
