#!/usr/bin/env bash
# tracker_ops.sh - Provider-agnostic issue-tracker operations dispatcher.
# Engines: native gh/glab issue commands and linear_ops.sh; jira is MCP-only.
#

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
[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && {
    usage
    exit 0
}

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "tracker-ops: $*" >&2; else printf '%s\n' "tracker-ops: $*" >&2; fi; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${SCRIPT_DIR}/tracker_registry.py"
LINEAR_OPS="${LINEAR_OPS_BIN:-${SCRIPT_DIR}/linear_ops.sh}"
CANONICAL_STATUSES=(planned in-progress needs-review "done")

valid_provider() { case "$1" in github | gitlab | linear | jira) return 0 ;; *) return 1 ;; esac }

resolve_provider() {
    local p=""
    if [[ -n "${FORCED_PROVIDER:-}" ]]; then
        p="${FORCED_PROVIDER}"
    elif [[ -n "${MANIFEST_TRACKER:-}" ]]; then
        p="${MANIFEST_TRACKER}"
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
[[ $# -eq 0 ]] && {
    usage >&2
    exit 1
}
verb="$1"
shift

provider=$(resolve_provider) || exit 1

if [[ "${provider}" == "jira" ]]; then
    if [[ "${verb}" == "resolve-provider" ]]; then
        echo jira
        exit 0
    fi
    err "unsupported-in-context: jira access is MCP-only; run from agent context"
    err "(registry: tracker_providers.yml providers.jira.access)"
    exit 3
fi

engine() {
    local op="${1:-}"
    shift
    if [[ "${provider}" == "linear" ]]; then
        bash "${LINEAR_OPS}" "${op}" "$@"
        return
    fi
    case "${op}" in
        issue-view)
            if [[ "${provider}" == github ]]; then gh issue view "$@"; else glab issue view "$@"; fi
            ;;
        issue-list)
            if [[ "${provider}" == github ]]; then
                gh issue list "$@"
            else
                local args=() arg
                while (($#)); do
                    arg="$1"
                    shift
                    case "${arg}" in
                        --state)
                            case "${1:-open}" in open) ;; closed) args+=(--closed) ;; all) args+=(--all) ;; esac
                            shift
                            ;;
                        --limit)
                            args+=(--per-page "${1:-}")
                            shift
                            ;;
                        *) args+=("${arg}") ;;
                    esac
                done
                glab issue list "${args[@]+"${args[@]}"}"
            fi
            ;;
        issue-create)
            if [[ "${provider}" == github ]]; then gh issue create "$@"; else glab issue create "$@"; fi
            ;;
        issue-close)
            if [[ "${provider}" == github ]]; then gh issue close "$@"; else glab issue close "$@"; fi
            ;;
        issue-comment)
            local n="$1" body=""
            shift
            if [[ "${1:-}" == "--body" || "${1:-}" == "--message" ]]; then
                body="${2:-}"
                shift 2
            else
                body="${1:-}"
                shift || true
            fi
            if [[ "${provider}" == github ]]; then gh issue comment "${n}" --body "${body}" "$@"; else glab issue note "${n}" --message "${body}" "$@"; fi
            ;;
        issue-edit)
            local n="$1"
            shift
            if [[ "${provider}" == github ]]; then gh issue edit "${n}" "$@"; else glab issue update "${n}" "$@"; fi
            ;;
        *)
            err "unsupported native issue operation: ${op}"
            return 1
            ;;
    esac
}

status_name() { python3 "${REGISTRY}" status "${provider}" "$1"; }

case "${verb}" in
    resolve-provider) echo "${provider}" ;;
    issue-list | issue-view | issue-create | issue-close)
        engine "${verb}" "$@"
        ;;
    issue-comment)
        case "${provider}" in
            github | gitlab)
                # Preserve positional N TEXT as one native CLI body value.
                # Provider dispatch happens inside engine.
                engine issue-comment "$@"
                ;;
            linear)
                # linear_ops.sh's cmd_issue_comment has no positional-text
                # support: it requires every arg after the identifier to be
                # Translate the documented `issue-comment N TEXT` contract into
                # `N --body TEXT` for Linear while preserving flag-style bodies.
                # guard so already-flag-style invocations (--body, --body-file,
                # or a TEXT that itself starts with "-") pass through unchanged.
                if [[ $# -ge 2 && "${2:0:1}" != "-" ]]; then
                    n="$1" body="$2"
                    shift 2
                    engine issue-comment "${n}" --body "${body}" "$@"
                else
                    engine issue-comment "$@"
                fi
                ;;
        esac
        ;;
    issue-label)
        case "${provider}" in
            github)
                engine issue-edit "$@"
                ;;
            gitlab)
                n="$1"
                shift
                args=()
                while (($#)); do
                    case "$1" in
                        --add-label)
                            args+=(--label "$2")
                            shift 2
                            ;;
                        --remove-label)
                            args+=(--unlabel "$2")
                            shift 2
                            ;;
                        *)
                            args+=("$1")
                            shift
                            ;;
                    esac
                done
                engine issue-edit "${n}" "${args[@]+"${args[@]}"}"
                ;;
            linear)
                err "issue-label not implemented for linear (registry documents the mapping; see spec §4.1)"
                exit 4
                ;;
        esac
        ;;
    issue-transition)
        n="${1:-}" target="${2:-}"
        [[ -n "${n}" && -n "${target}" ]] || {
            err "usage: issue-transition N CANONICAL_STATUS"
            exit 1
        }
        case "${provider}" in
            github)
                args=("${n}")
                for s in "${CANONICAL_STATUSES[@]}"; do [[ "${s}" != "${target}" ]] && args+=(--remove-label "${s}"); done
                args+=(--add-label "$(status_name "${target}")")
                engine issue-edit "${args[@]+"${args[@]}"}"
                ;;
            gitlab)
                args=("${n}")
                for s in "${CANONICAL_STATUSES[@]}"; do [[ "${s}" != "${target}" ]] && args+=(--unlabel "${s}"); done
                args+=(--label "$(status_name "${target}")")
                engine issue-edit "${args[@]+"${args[@]}"}"
                ;;
            linear)
                engine transition-state --identifier "${n}" --state "$(status_name "${target}")"
                ;;
        esac
        ;;
    duplicate-mark)
        n="${1:-}"
        [[ -n "${n}" ]] || {
            err "usage: duplicate-mark N --duplicate-of M"
            exit 1
        }
        shift
        [[ "${1:-}" == "--duplicate-of" ]] || {
            err "usage: duplicate-mark N --duplicate-of M"
            exit 1
        }
        primary="${2:-}"
        [[ -n "${primary}" ]] || {
            err "usage: duplicate-mark N --duplicate-of M"
            exit 1
        }
        case "${provider}" in
            linear) engine issue-mark-duplicate "${n}" --duplicate-of "${primary}" ;;
            github)
                engine issue-comment "${n}" "Duplicate of #${primary}"
                engine issue-edit "${n}" --add-label duplicate
                engine issue-close "${n}"
                ;;
            gitlab)
                engine issue-comment "${n}" "Duplicate of #${primary}"
                engine issue-edit "${n}" --label duplicate
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
