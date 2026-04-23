#!/bin/bash
# shellcheck disable=SC2001,SC2004,SC2016,SC2059,SC2129,SC2181
# Generate Cursor .mdc rule files from canonical SKILL.md sources.
# Prevents drift between .claude/skills/ and .cursor/rules/.
#
# Usage: generate_cursor_rules.sh [--dry-run] [--verbose]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SKILLS_DIR="$REPO_ROOT/configs/claude/skills"
RULES_DIR="$REPO_ROOT/configs/cursor/rules"

DRY_RUN=false
VERBOSE=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --verbose) VERBOSE=true ;;
        -h | --help)
            echo "Usage: $(basename "$0") [--dry-run] [--verbose]"
            echo "Regenerate configs/cursor/rules/*.mdc from configs/claude/skills/*/SKILL.md"
            exit 0
            ;;
    esac
done

log() { if $VERBOSE; then echo "[INFO] $*"; fi; }

created=0
updated=0
skipped=0

for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name="$(basename "$skill_dir")"
    skill_file="$skill_dir/SKILL.md"
    rule_file="$RULES_DIR/$skill_name.mdc"

    if [[ ! -f "$skill_file" ]]; then
        log "Skip $skill_name: no SKILL.md"
        continue
    fi

    # Extract description from YAML front matter (handles both inline and block scalar |)
    description=""
    if head -1 "$skill_file" | grep -q '^---'; then
        front_matter=$(sed -n '2,/^---$/p' "$skill_file" | sed '$d')
        desc_line=$(echo "$front_matter" | grep '^description:' | head -1)
        desc_value=$(echo "$desc_line" | sed 's/^description:[[:space:]]*//')

        if [[ "$desc_value" == "|" || "$desc_value" == "|-" || -z "$desc_value" ]]; then
            # Block scalar: collect indented lines after "description: |"
            description=$(echo "$front_matter" |
                sed -n '/^description:/,/^[^ ]/p' |
                tail -n +2 |
                grep '^  ' |
                sed 's/^  //' |
                tr '\n' ' ' |
                sed 's/[[:space:]]*$//')
        else
            # Inline value
            description=$(echo "$desc_value" | sed 's/^"//' | sed 's/"$//')
        fi
    fi
    description="${description:-$skill_name skill}"

    # Build thin wrapper content
    content="---
description: \"$description\"
globs: \".claude/skills/$skill_name/**\"
alwaysApply: false
---

# ${skill_name}

${description}

<!-- Auto-generated from .claude/skills/$skill_name/SKILL.md -->
<!-- Regenerate with: .claude/scripts/generate_cursor_rules.sh -->

Refer to \`.cursor/skills/$skill_name/SKILL.md\` for the full skill definition.
"

    if [[ -f "$rule_file" ]]; then
        existing=$(cat "$rule_file")
        if [[ "$existing" == "$content" ]]; then
            log "Skip $skill_name: unchanged"
            skipped=$((skipped + 1))
            continue
        fi
        if $DRY_RUN; then
            echo "[DRY-RUN] Would update: $rule_file"
            updated=$((updated + 1))
            continue
        fi
        echo "$content" > "$rule_file"
        log "Updated: $rule_file"
        updated=$((updated + 1))
    else
        if $DRY_RUN; then
            echo "[DRY-RUN] Would create: $rule_file"
            created=$((created + 1))
            continue
        fi
        echo "$content" > "$rule_file"
        log "Created: $rule_file"
        created=$((created + 1))
    fi
done

echo "Cursor rules: $created created, $updated updated, $skipped unchanged"
