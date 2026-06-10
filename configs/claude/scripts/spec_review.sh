#!/usr/bin/env bash
# spec_review.sh — cross-reference spec/plan/tasks artifacts for consistency via
# an independent reviewer CLI (default: agy / Antigravity). Analysis-only: never
# edits artifacts. Reviewer is the injectable SPEC_REVIEW_CLI seam. Front-end-agnostic — the
# /spec-review skill, the save hook, and any future CLI all wrap this script.
#
# Usage: spec_review.sh [--spec F] [--plan F] [--tasks F] [--silent] [--format tree|json] [ROOT]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_REVIEW_CLI="${SPEC_REVIEW_CLI:-agy}"
SPEC_REVIEW_TEMPLATE="${SPEC_REVIEW_TEMPLATE:-${SCRIPT_DIR}/../prompts/spec_review.md}"
SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE:-.spec-review}"
SPEC_REVIEW_NO_DETACH="${SPEC_REVIEW_NO_DETACH:-}"

SPEC=""; PLAN=""; TASKS=""; SILENT=false; FORMAT="tree"; ROOT="."

err() { echo "spec-review: $*" >&2; }
usage() {
    cat <<'EOF'
spec-review — cross-reference spec/plan/tasks for consistency (Antigravity/agy, analysis-only)

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

# assemble_prompt TEMPLATE "role\tpath"...  ->  full prompt on stdout
assemble_prompt() {
    local template="$1"; shift
    local artfile line role path
    artfile="$(mktemp)"
    for line in "$@"; do
        role="${line%%$'\t'*}"; path="${line#*$'\t'}"
        {
            printf '=== %s: %s ===\n' "$(printf '%s' "$role" | tr '[:lower:]' '[:upper:]')" "$path"
            cat "$path"
            printf '\n\n'
        } >> "$artfile"
    done
    # Substitute {{ARTIFACTS}} inline: print lines before the marker, inject
    # artifact file contents, then continue with lines after the marker.
    # Capture awk's status so the temp file is removed even on failure (set -e
    # would otherwise abort before cleanup). bash 3.2-safe (no RETURN trap).
    local rc=0
    awk -v artfile="$artfile" '
        /\{\{ARTIFACTS\}\}/ {
            while ((getline ln < artfile) > 0) print ln
            next
        }
        { print }
    ' "$template" || rc=$?
    rm -f "$artfile"
    return "$rc"
}

# run_reviewer PROMPT -> raw reviewer output. stdin carries the prompt body; the -p
# instruction is short. Errors propagate (caller decides fail-open vs surface).
run_reviewer() {
    local prompt="$1"
    printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" -p "Cross-reference the artifacts above per the instructions; output only the specified blocks or NO_ISSUES."
}

# format_findings RAW FORMAT [COUNT] -> formatted output. NO_ISSUES -> clean
# message (with the artifact count when COUNT is supplied).
format_findings() {
    local raw="$1" fmt="${2:-tree}" count="${3:-}"
    if [[ -z "${raw//[[:space:]]/}" || "$raw" == *NO_ISSUES* ]]; then
        if [[ "$fmt" == "json" ]]; then
            echo "[]"
        elif [[ -n "$count" ]]; then
            echo "✓ No inconsistencies found across ${count} artifacts."
        else
            echo "✓ No inconsistencies found."
        fi
        return 0
    fi
    if [[ "$fmt" == "json" ]]; then
        # Minimal: wrap raw blocks as a single JSON string element (tolerant).
        printf '[%s]\n' "$(printf '%s' "$raw" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
    else
        printf '%s\n' "$raw"
    fi
}

# Stable combined-content hash of the given files.
content_hash() {
    cat "$@" 2>/dev/null | shasum | awk '{print $1}'
}

# Gating for silent/hook mode. Returns 0 (run) or 1 (skip, with reason on stdout).
# Records the hash in $SPEC_REVIEW_STATE/.last-run only when it decides to run.
should_run_silent() {
    local root="${1:-.}" state="$SPEC_REVIEW_STATE"
    # Collect paths into an array (bash 3.2-safe) so paths with spaces hash
    # correctly and the count is exact (no printf/grep off-by-one).
    local paths=() line
    while IFS= read -r line; do [[ -n "$line" ]] && paths+=("$line"); done \
        < <(discover_artifacts "$root" | cut -f2)
    if [[ "${#paths[@]}" -lt 2 ]]; then echo "skip: fewer than 2 artifacts"; return 1; fi
    mkdir -p "$state"
    local now prev="$state/.last-run"
    now="$(content_hash ${paths[@]+"${paths[@]}"})"
    if [[ -f "$prev" && "$(cat "$prev")" == "$now" ]]; then
        echo "skip: unchanged"; return 1
    fi
    echo "$now" > "$prev"
    return 0
}

# Emit role<TAB>path lines from explicit --spec/--plan/--tasks if any were given,
# else auto-discover under ROOT.
resolve_artifacts() {
    local root="${1:-.}"
    if [[ -n "$SPEC" || -n "$PLAN" || -n "$TASKS" ]]; then
        [[ -n "$SPEC" ]]  && printf 'spec\t%s\n'  "$SPEC"
        [[ -n "$PLAN" ]]  && printf 'plan\t%s\n'  "$PLAN"
        [[ -n "$TASKS" ]] && printf 'tasks\t%s\n' "$TASKS"
        return 0
    fi
    discover_artifacts "$root"
}

# review ROOT FORMAT -> resolve, assemble, run reviewer, format. Used on-demand.
review() {
    local root="${1:-.}" fmt="${2:-tree}"
    local arts=() line
    while IFS= read -r line; do [[ -n "$line" ]] && arts+=("$line"); done < <(resolve_artifacts "$root")
    if [[ "${#arts[@]}" -eq 0 ]]; then echo "spec-review: nothing to review (no artifacts found)"; return 0; fi
    echo "[spec-review] Cross-referencing project artifacts with Antigravity (agy)…"
    local prompt raw; prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" ${arts[@]+"${arts[@]}"})"
    raw="$(run_reviewer "$prompt")"
    format_findings "$raw" "$fmt" "${#arts[@]}"
}

# The actual review for hook mode, fail-open. Writes feedback.md atomically.
_silent_review_inline() {
    local root="$1" state="$SPEC_REVIEW_STATE"
    mkdir -p "$state"
    local arts=() line prompt raw
    while IFS= read -r line; do [[ -n "$line" ]] && arts+=("$line"); done < <(discover_artifacts "$root")
    [[ "${#arts[@]}" -eq 0 ]] && return 0   # defensive: nothing to review (set -u safe)
    prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" ${arts[@]+"${arts[@]}"})"
    if ! raw="$(run_reviewer "$prompt" 2>>"$state/error.log")"; then
        return 0   # fail-open: reviewer failed, never block
    fi
    format_findings "$raw" "tree" > "$state/feedback.md.tmp" && mv "$state/feedback.md.tmp" "$state/feedback.md"
}

# Silent/hook entry: gate, single-flight lock, detach the reviewer call.
run_silent() {
    local root="${1:-.}" state="$SPEC_REVIEW_STATE"
    if ! should_run_silent "$root" >/dev/null; then
        return 0   # gate said skip (fewer than 2 artifacts / unchanged)
    fi
    mkdir -p "$state"
    # Self-heal a stale lock left by a crashed prior run (older than 10 min), so a
    # killed detached review can never permanently disable the hook.
    if [[ -d "$state/.lock" ]] && find "$state/.lock" -maxdepth 0 -mmin +10 2>/dev/null | grep -q .; then
        rmdir "$state/.lock" 2>/dev/null || true
    fi
    # Single-flight lock: skip if a review is already in flight.
    if ! mkdir "$state/.lock" 2>/dev/null; then return 0; fi
    # `|| true` after the review so an unexpected non-zero (disk full, etc.) never
    # skips the lock release or breaks the fail-open contract.
    if [[ -n "$SPEC_REVIEW_NO_DETACH" ]]; then
        _silent_review_inline "$root" || true; rmdir "$state/.lock" 2>/dev/null || true
    else
        # Detach so the agent loop never waits on the reviewer; release lock when done.
        ( _silent_review_inline "$root" || true; rmdir "$state/.lock" 2>/dev/null || true ) >/dev/null 2>&1 &
        disown 2>/dev/null || true
    fi
    return 0
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; return 0; fi
    parse_args "$@" || return $?
    if [[ "$SILENT" == true ]]; then run_silent "$ROOT"; return 0; fi
    review "$ROOT" "$FORMAT"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
