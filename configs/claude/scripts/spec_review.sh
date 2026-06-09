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

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; return 0; fi
    parse_args "$@" || return $?
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
