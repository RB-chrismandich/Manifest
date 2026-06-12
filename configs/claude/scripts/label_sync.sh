#!/usr/bin/env bash
# label_sync.sh - Sync labels from labels.yml registry to GitHub, GitLab, and Linear
#
# Reads the canonical label registry and ensures all labels exist in each platform.
# Uses git_ops.sh for GitHub/GitLab and linear_ops.sh for Linear.
#
# Usage: label_sync.sh [options]
#
# Options:
#   --dry-run          Show what would be created without making changes
#   --platform <name>  Only sync to specific platform (github|gitlab|linear)
#   --team <key>       Linear team key for team-scoped labels
#   --config <path>    Path to labels.yml (default: auto-detect)
#   --validate         Only validate — report missing labels, don't create

set -euo pipefail

err() { echo "label-sync: $*" >&2; }

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Defaults
DRY_RUN=false
PLATFORM_FILTER=""
LINEAR_TEAM=""
VALIDATE_ONLY=false
LABELS_FILE=""

# Counters
CREATED=0
SKIPPED=0
FAILED=0

# --- Argument parsing ---

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --platform)
            PLATFORM_FILTER="$2"
            shift 2
            ;;
        --team)
            LINEAR_TEAM="$2"
            shift 2
            ;;
        --config)
            LABELS_FILE="$2"
            shift 2
            ;;
        --validate)
            VALIDATE_ONLY=true
            shift
            ;;
        -h | --help)
            echo "Usage: label_sync.sh [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run          Show what would be created"
            echo "  --platform <name>  Only sync to: github, gitlab, or linear"
            echo "  --team <key>       Linear team key for team-scoped labels"
            echo "  --config <path>    Path to labels.yml"
            echo "  --validate         Only report missing labels, don't create"
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            exit 1
            ;;
    esac
done

# --- Locate labels.yml ---

find_labels_file() {
    if [[ -n "$LABELS_FILE" ]]; then
        if [[ -f "$LABELS_FILE" ]]; then
            echo "$LABELS_FILE"
            return 0
        fi
        err "Labels file not found: $LABELS_FILE"
        return 1
    fi

    # Search order: repo-local, then deployed
    local candidates=(
        ".claude/config/labels.yml"
        "${HOME}/.claude/config/labels.yml"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -f "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done

    err "labels.yml not found. Searched: ${candidates[*]}"
    return 1
}

# --- Parse labels.yml with python3 ---

parse_labels() {
    local file="$1"
    # Path passed via argv, never interpolated into Python source (FR-009):
    # a path containing quotes must be data, not code.
    python3 -c "
import yaml, json, sys
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
labels = data.get('labels', [])
json.dump(labels, sys.stdout)
" "$file"
}

# --- Detect current git platform ---

detect_git_platform() {
    if [[ -f "${SCRIPT_DIR}/git_platform.sh" ]]; then
        bash "${SCRIPT_DIR}/git_platform.sh" 2> /dev/null || echo "none"
    else
        echo "none"
    fi
}

# --- Check if Linear is available ---

linear_available() {
    # linear_ops.sh calls the Linear API via curl, so only a usable API key
    # counts — an MCP registry entry does not (issue #312).
    if [[ -f "${SCRIPT_DIR}/linear_ops.sh" ]]; then
        if [[ -n "${LINEAR_API_KEY:-}" ]]; then
            return 0
        fi
        if [[ -s "${HOME}/.config/linear/token" ]]; then
            return 0
        fi
    fi
    return 1
}

# --- Sync a single label to GitHub/GitLab ---

sync_git_label() {
    local name="$1"
    local color="$2"
    local description="$3"

    if [[ "$DRY_RUN" == "true" ]] || [[ "$VALIDATE_ONLY" == "true" ]]; then
        echo -e "  ${BLUE}[dry-run]${NC} Would create: ${name} (${color}) on git platform"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi

    if bash "${SCRIPT_DIR}/git_ops.sh" label-create "$name" --color "$color" --description "$description" --force 2> /dev/null; then
        echo -e "  ${GREEN}[created]${NC} ${name} (${color})"
        CREATED=$((CREATED + 1))
    else
        echo -e "  ${YELLOW}[exists]${NC} ${name} (${color})"
        SKIPPED=$((SKIPPED + 1))
    fi
}

# --- Sync a single label to Linear ---

sync_linear_label() {
    local name="$1"
    local color="$2"
    local description="$3"

    local team_args=()
    if [[ -n "$LINEAR_TEAM" ]]; then
        team_args=(--team "$LINEAR_TEAM")
    fi

    if [[ "$DRY_RUN" == "true" ]] || [[ "$VALIDATE_ONLY" == "true" ]]; then
        echo -e "  ${BLUE}[dry-run]${NC} Would create: ${name} (${color}) on Linear"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi

    # ${arr[@]+"${arr[@]}"} expands to nothing when the array is empty — required
    # because macOS Bash 3.2 treats "${empty[@]}" as an unbound var under `set -u`.
    if bash "${SCRIPT_DIR}/linear_ops.sh" label-create --name "$name" --color "$color" --description "$description" ${team_args[@]+"${team_args[@]}"} 2> /dev/null; then
        echo -e "  ${GREEN}[created]${NC} ${name} (${color}) on Linear"
        CREATED=$((CREATED + 1))
    else
        echo -e "  ${YELLOW}[exists]${NC} ${name} (${color}) on Linear"
        SKIPPED=$((SKIPPED + 1))
    fi
}

# --- Main ---

main() {
    local labels_file
    labels_file=$(find_labels_file)

    echo -e "${BLUE}Label Sync${NC}"
    echo "Registry: ${labels_file}"
    echo ""

    # Parse labels
    local labels_json
    labels_json=$(parse_labels "$labels_file")

    local label_count
    label_count=$(echo "$labels_json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
    echo "Found ${label_count} labels in registry"
    echo ""

    # Detect platforms
    local git_platform
    git_platform=$(detect_git_platform)

    local has_linear=false
    if linear_available; then
        has_linear=true
    fi

    # Process each label (use process substitution to avoid subshell counter issue)
    while IFS='|' read -r name color description platforms; do

        echo -e "${GREEN}Label:${NC} ${name}"

        # Sync to git platform (GitHub/GitLab)
        if [[ "$platforms" == *"$git_platform"* ]]; then
            if [[ -z "$PLATFORM_FILTER" ]] || [[ "$PLATFORM_FILTER" == "$git_platform" ]]; then
                if [[ "$git_platform" != "none" ]]; then
                    sync_git_label "$name" "$color" "$description"
                fi
            fi
        fi

        # Sync to Linear
        if [[ "$platforms" == *"linear"* ]]; then
            if [[ -z "$PLATFORM_FILTER" ]] || [[ "$PLATFORM_FILTER" == "linear" ]]; then
                if [[ "$has_linear" == "true" ]]; then
                    sync_linear_label "$name" "$color" "$description"
                else
                    echo -e "  ${YELLOW}[skip]${NC} Linear not configured"
                fi
            fi
        fi

    done < <(echo "$labels_json" | python3 -c "
import json, sys
labels = json.load(sys.stdin)
for label in labels:
    platforms = ','.join(label.get('platforms', []))
    print(f\"{label['name']}|{label['color']}|{label.get('description', '')}|{platforms}\")
")

    echo ""
    echo -e "${BLUE}Summary${NC}"
    echo "  Created: ${CREATED}"
    echo "  Skipped/Exists: ${SKIPPED}"
    echo "  Failed: ${FAILED}"

    if [[ "$FAILED" -gt 0 ]]; then
        exit 1
    fi
}

main
