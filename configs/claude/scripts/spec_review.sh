#!/usr/bin/env bash
# spec_review.sh — cross-reference spec/plan/tasks artifacts for consistency via
# the gemini CLI. Analysis-only: never edits artifacts. Front-end-agnostic — the
# /spec-review skill, the save hook, and any future CLI all wrap this script.
#
# Usage: spec_review.sh [--spec F] [--plan F] [--tasks F] [--silent] [--format tree|json] [ROOT]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_REVIEW_GEMINI="${SPEC_REVIEW_GEMINI:-gemini}"
SPEC_REVIEW_TEMPLATE="${SPEC_REVIEW_TEMPLATE:-${SCRIPT_DIR}/../prompts/spec_review.md}"
SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE:-.spec-review}"
SPEC_REVIEW_NO_DETACH="${SPEC_REVIEW_NO_DETACH:-}"

SPEC=""; PLAN=""; TASKS=""; SILENT=false; FORMAT="tree"; ROOT="."

err() { echo "spec-review: $*" >&2; }
usage() {
    cat <<'EOF'
spec-review — cross-reference spec/plan/tasks for consistency (Gemini, analysis-only)

Usage: spec_review.sh [--spec F] [--plan F] [--tasks F] [--silent] [--format tree|json] [ROOT]

  --spec/--plan/--tasks F  explicit artifact paths (else auto-discover under ROOT)
  --silent                 hook mode: hash-gated, detached, writes .spec-review/feedback.md
  --format tree|json       output format (default: tree)
  ROOT                     project root to discover in (default: .)
EOF
}

parse_args() {
    # shellcheck disable=SC2034  # vars consumed by future discovery/invoke tasks
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --spec)  SPEC="$2"; shift 2 ;;
            --plan)  PLAN="$2"; shift 2 ;;
            --tasks) TASKS="$2"; shift 2 ;;
            --silent) SILENT=true; shift ;;
            --format) FORMAT="$2"; shift 2 ;;
            -h|--help) usage; return 0 ;;
            -*) err "unknown flag: $1"; return 2 ;;
            *) ROOT="$1"; shift ;;
        esac
    done
}

# Print "role\tpath" lines for discovered artifacts. speckit: spec/plan/tasks.md
# (cwd or specs/<n>/). superpowers: newest *-design.md + newest plans/*.md (tasks
# are embedded in the plan, so no tasks line). Newest = name sort (date-prefixed).
discover_artifacts() {
    local root="${1:-.}" sp pl
    # speckit: specs/<n>/ first, then cwd
    # shellcheck disable=SC2012  # ls used intentionally; files are date-prefixed, no special chars
    sp=$(ls -1 "$root"/specs/*/spec.md 2>/dev/null | sort | tail -1 || true)
    [[ -z "$sp" && -f "$root/spec.md" ]] && sp="$root/spec.md"
    if [[ -n "$sp" ]]; then
        local d; d="$(dirname "$sp")"
        printf 'spec\t%s\n' "$sp"
        [[ -f "$d/plan.md" ]]  && printf 'plan\t%s\n'  "$d/plan.md"
        [[ -f "$d/tasks.md" ]] && printf 'tasks\t%s\n' "$d/tasks.md"
        return 0
    fi
    # superpowers: newest design + newest plan (tasks embedded in plan)
    # shellcheck disable=SC2012  # ls used intentionally; files are date-prefixed, no special chars
    sp=$(ls -1 "$root"/docs/superpowers/specs/*-design.md 2>/dev/null | sort | tail -1 || true)
    # shellcheck disable=SC2012  # ls used intentionally; files are date-prefixed, no special chars
    pl=$(ls -1 "$root"/docs/superpowers/plans/*.md 2>/dev/null | sort | tail -1 || true)
    [[ -n "$sp" ]] && printf 'spec\t%s\n' "$sp"
    [[ -n "$pl" ]] && printf 'plan\t%s\n' "$pl"
    return 0
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; return 0; fi
    parse_args "$@" || return $?
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
