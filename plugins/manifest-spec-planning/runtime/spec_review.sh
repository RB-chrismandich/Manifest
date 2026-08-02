#!/usr/bin/env bash
# Cross-reference spec/plan/tasks with one installed native reviewer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_REVIEW_CLI="${SPEC_REVIEW_CLI:-agy}"
SPEC_REVIEW_PROVIDER="${SPEC_REVIEW_PROVIDER:-antigravity}"
SPEC_REVIEW_MODEL="${SPEC_REVIEW_MODEL:-}"
SPEC_REVIEW_CONFIG="${SPEC_REVIEW_CONFIG:-$SCRIPT_DIR/config/review_models.json}"
SPEC_REVIEW_TEMPLATE="${SPEC_REVIEW_TEMPLATE:-$SCRIPT_DIR/prompts/spec_review.md}"
SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE:-.spec-review}"
SPEC_REVIEW_NO_DETACH="${SPEC_REVIEW_NO_DETACH:-}"
SPEC_REVIEW_TIMEOUT="${SPEC_REVIEW_TIMEOUT:-600}"

SPEC=""
PLAN=""
TASKS=""
SILENT=false
FORMAT="tree"
ROOT="."

err() { printf '%s\n' "spec-review: $*" >&2; }

usage() {
    cat << 'EOF'
spec-review — cross-reference spec/plan/tasks for consistency

Usage: spec_review.sh [--spec F] [--plan F] [--tasks F] [--silent] [--format tree|json] [ROOT]

  --spec/--plan/--tasks F  explicit artifact paths (else auto-discover under ROOT)
  --silent                 hash-gated background review into .spec-review/feedback.md
  --format tree|json       output format (default: tree)
  --mode product|technical select a lifecycle review prompt/state namespace
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --spec)
                SPEC="${2:-}"
                shift 2
                ;;
            --plan)
                PLAN="${2:-}"
                shift 2
                ;;
            --tasks)
                TASKS="${2:-}"
                shift 2
                ;;
            --silent)
                SILENT=true
                shift
                ;;
            --format)
                FORMAT="${2:-}"
                shift 2
                ;;
            --mode)
                case "${2:-}" in
                    product) SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE%/}/product" ;;
                    technical)
                        SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE%/}/technical"
                        SPEC_REVIEW_TEMPLATE="$SCRIPT_DIR/prompts/spec_review_technical.md"
                        ;;
                    *)
                        err "invalid --mode: '${2:-}' (use product|technical)"
                        return 2
                        ;;
                esac
                shift 2
                ;;
            -h | --help)
                usage
                return 0
                ;;
            -*)
                err "unknown flag: $1"
                return 2
                ;;
            *)
                ROOT="$1"
                shift
                ;;
        esac
    done
    [[ "$FORMAT" == "tree" || "$FORMAT" == "json" ]] || {
        err "invalid format: $FORMAT"
        return 2
    }
}

discover_artifacts() {
    local root="${1:-.}" spec plan dir
    if [[ -f "$root" ]]; then
        printf 'spec\t%s\n' "$root"
        case "$root" in
            */docs/superpowers/specs/*.md)
                dir="${root%/specs/*}"
                plan=$(find "$dir/plans" -maxdepth 1 -type f -name '*.md' 2> /dev/null | sort | tail -1 || true)
                [[ -n "$plan" ]] && printf 'plan\t%s\n' "$plan"
                ;;
            *)
                dir="$(dirname "$root")"
                [[ -f "$dir/plan.md" ]] && printf 'plan\t%s\n' "$dir/plan.md"
                [[ -f "$dir/tasks.md" ]] && printf 'tasks\t%s\n' "$dir/tasks.md"
                ;;
        esac
        return 0
    fi
    spec=$(find "$root/specs" -mindepth 2 -maxdepth 2 -type f -name spec.md 2> /dev/null | sort | tail -1 || true)
    [[ -z "$spec" && -f "$root/spec.md" ]] && spec="$root/spec.md"
    if [[ -n "$spec" ]]; then
        dir="$(dirname "$spec")"
        printf 'spec\t%s\n' "$spec"
        [[ -f "$dir/plan.md" ]] && printf 'plan\t%s\n' "$dir/plan.md"
        [[ -f "$dir/tasks.md" ]] && printf 'tasks\t%s\n' "$dir/tasks.md"
        return 0
    fi
    spec=$(find "$root/docs/superpowers/specs" -maxdepth 1 -type f -name '*-design.md' 2> /dev/null | sort | tail -1 || true)
    plan=$(find "$root/docs/superpowers/plans" -maxdepth 1 -type f -name '*.md' 2> /dev/null | sort | tail -1 || true)
    [[ -n "$spec" ]] && printf 'spec\t%s\n' "$spec"
    [[ -n "$plan" ]] && printf 'plan\t%s\n' "$plan"
}

resolve_artifacts() {
    if [[ -n "$SPEC" || -n "$PLAN" || -n "$TASKS" ]]; then
        [[ -n "$SPEC" ]] && printf 'spec\t%s\n' "$SPEC"
        [[ -n "$PLAN" ]] && printf 'plan\t%s\n' "$PLAN"
        [[ -n "$TASKS" ]] && printf 'tasks\t%s\n' "$TASKS"
    else
        discover_artifacts "${1:-.}"
    fi
}

assemble_prompt() {
    local template="$1" line role path
    shift
    while IFS= read -r line; do
        if [[ "$line" == *'{{ARTIFACTS}}'* ]]; then
            for line in "$@"; do
                role="${line%%$'\t'*}"
                path="${line#*$'\t'}"
                printf '=== %s: %s ===\n' "$(printf '%s' "$role" | tr '[:lower:]' '[:upper:]')" "$path"
                cat "$path"
                printf '\n\n'
            done
        else
            printf '%s\n' "$line"
        fi
    done < "$template"
}

resolve_review_model() {
    if [[ -n "$SPEC_REVIEW_MODEL" ]]; then
        printf '%s' "$SPEC_REVIEW_MODEL"
        return 0
    fi
    python3 - "$SPEC_REVIEW_CONFIG" "$SPEC_REVIEW_PROVIDER" << 'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as config_file:
        config = json.load(config_file)
    print(config["providers"][sys.argv[2]]["models"].get("advanced", ""), end="")
except (KeyError, OSError, TypeError, ValueError):
    pass
PY
}

run_reviewer() {
    local prompt="$1" model binary
    model="$(resolve_review_model)"
    binary="$(basename "$SPEC_REVIEW_CLI")"
    case "$binary" in
        agy)
            if [[ -n "$model" ]]; then
                "$SPEC_REVIEW_CLI" --model "$model" --print "$prompt"
            else
                "$SPEC_REVIEW_CLI" --print "$prompt"
            fi
            ;;
        cursor-agent)
            local args=(--print --output-format text --mode ask)
            [[ -n "$model" ]] && args+=(--model "$model")
            "$SPEC_REVIEW_CLI" "${args[@]}" "$prompt"
            ;;
        gemini)
            local gemini_args=()
            [[ -n "$model" ]] && gemini_args+=(-m "$model")
            "$SPEC_REVIEW_CLI" "${gemini_args[@]+"${gemini_args[@]}"}" -p "$prompt"
            ;;
        codex)
            local codex_args=(exec --color never)
            [[ -n "$model" ]] && codex_args+=(--model "$model")
            printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" "${codex_args[@]}" -
            ;;
        claude)
            local claude_args=()
            [[ -n "$model" ]] && claude_args+=(--model "$model")
            printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" "${claude_args[@]+"${claude_args[@]}"}" -p
            ;;
        *) printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" ;;
    esac
}

validate_findings() {
    local raw="$1"
    if [[ "$raw" == *NO_ISSUES* || "$raw" == *"CLARIFICATION REQUIRED"* ]]; then
        return 0
    fi
    err "unverifiable reviewer output (expected NO_ISSUES or CLARIFICATION REQUIRED)"
    return 3
}

format_findings() {
    local raw="$1" fmt="${2:-tree}" count="${3:-}"
    if [[ "$raw" == *NO_ISSUES* ]]; then
        if [[ "$fmt" == "json" ]]; then
            printf '[]\n'
        elif [[ -n "$count" ]]; then
            printf 'No inconsistencies found across %s artifacts.\n' "$count"
        else
            printf 'No inconsistencies found.\n'
        fi
    elif [[ "$fmt" == "json" ]]; then
        printf '%s' "$raw" | python3 -c 'import json,sys; print(json.dumps([sys.stdin.read()]))'
    else
        printf '%s\n' "$raw"
    fi
}

content_hash() { cat "$@" 2> /dev/null | shasum | awk '{print $1}'; }

should_run_silent() {
    local root="${1:-.}" state="$SPEC_REVIEW_STATE" now prev line
    local paths=()
    while IFS= read -r line; do [[ -n "$line" ]] && paths+=("${line#*$'\t'}"); done < <(discover_artifacts "$root")
    if [[ "${#paths[@]}" -lt 2 ]]; then
        printf 'skip: fewer than 2 artifacts\n'
        return 1
    fi
    mkdir -p "$state"
    now="$(content_hash "${paths[@]+"${paths[@]}"}")"
    prev="$state/.last-run"
    if [[ -f "$prev" && "$(cat "$prev")" == "$now" ]]; then
        printf 'skip: unchanged\n'
        return 1
    fi
    printf '%s\n' "$now"
}

review() {
    local root="${1:-.}" fmt="${2:-tree}" line prompt raw
    local artifacts=()
    while IFS= read -r line; do [[ -n "$line" ]] && artifacts+=("$line"); done < <(resolve_artifacts "$root")
    if [[ "${#artifacts[@]}" -eq 0 ]]; then
        printf 'spec-review: nothing to review (no artifacts found)\n'
        return 0
    fi
    prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" "${artifacts[@]+"${artifacts[@]}"}")"
    raw="$(run_reviewer "$prompt")" || return $?
    validate_findings "$raw" || return $?
    format_findings "$raw" "$fmt" "${#artifacts[@]}"
}

_silent_review_inline() {
    local root="$1" review_hash="$2" state="$SPEC_REVIEW_STATE"
    mkdir -p "$state"
    if review "$root" tree > "$state/feedback.md.tmp" 2>> "$state/error.log" &&
        mv "$state/feedback.md.tmp" "$state/feedback.md"; then
        printf '%s\n' "$review_hash" > "$state/.last-run"
    else
        rm -f "$state/feedback.md.tmp"
    fi
}

run_silent() {
    local root="${1:-.}" review_hash
    review_hash="$(should_run_silent "$root")" || return 0
    if [[ -n "$SPEC_REVIEW_NO_DETACH" ]]; then
        _silent_review_inline "$root" "$review_hash"
    else
        (_silent_review_inline "$root" "$review_hash") > /dev/null 2>&1 &
    fi
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        usage
        return 0
    fi
    parse_args "$@" || return $?
    if [[ "$SILENT" == true ]]; then run_silent "$ROOT"; else review "$ROOT" "$FORMAT"; fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
