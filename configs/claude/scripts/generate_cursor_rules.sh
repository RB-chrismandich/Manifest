#!/bin/bash
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

    # Extract description from YAML front matter (handles inline values and
    # literal/folded block scalars: |, |-, |+, >, >-, >+)
    description=""
    if head -1 "$skill_file" | grep -q '^---'; then
        front_matter=$(sed -n '2,/^---$/p' "$skill_file" | sed '$d')
        # `|| true`: under `set -euo pipefail` a no-match grep would abort the
        # script; tolerate a SKILL.md with no description and fall back below.
        desc_line=$(echo "$front_matter" | grep '^description:' | head -1 || true)
        desc_value=$(echo "$desc_line" | sed 's/^description:[[:space:]]*//')

        if [[ "$desc_value" =~ ^[\|\>][+-]?$ || -z "$desc_value" ]]; then
            # Block scalar: collect indented lines after the indicator
            description=$(echo "$front_matter" |
                sed -n '/^description:/,/^[^ ]/p' |
                tail -n +2 |
                grep '^  ' |
                sed 's/^  //' |
                tr '\n' ' ' |
                sed 's/[[:space:]]*$//' || true)
        else
            # Inline value
            description=$(echo "$desc_value" | sed 's/^"//' | sed 's/"$//')
        fi
    fi
    description="${description:-$skill_name skill}"

    # Escape for a double-quoted YAML scalar: backslash first, then double
    # quote, so a description containing " (e.g. a quoted phrase like
    # ("still in progress")) doesn't terminate the frontmatter scalar early
    # and leave invalid YAML that Cursor can't load the rule from.
    description_yaml="${description//\\/\\\\}"
    description_yaml="${description_yaml//\"/\\\"}"

    # Build thin wrapper content
    content="---
description: \"$description_yaml\"
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
        # Compare against the exact bytes a write would produce. $(...) strips
        # trailing newlines, so capture with a sentinel to preserve them; the
        # write below is `echo "$content"`, which appends one newline beyond
        # $content's own. Comparing raw $content here would never match and the
        # unchanged branch would be dead code (every rule re-written each run).
        existing=$(cat "$rule_file"; printf x); existing="${existing%x}"
        if [[ "$existing" == "$content"$'\n' ]]; then
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

# --- Command discovery index rule (spec 362 / T015) ------------------------ #
# Emit an always-applied Cursor rule carrying the compact command index, so
# Cursor reaches the same always-loaded discovery parity as GEMINI.md/AGENTS.md.
# The index body comes from the Python generator (single source of truth); guard
# on python3+pyyaml so a machine lacking them still generates the per-skill
# rules above (CI has pyyaml, so drift is still caught there).
GEN_DOC="$REPO_ROOT/configs/claude/scripts/generate_commands_doc.py"
index_rule="$RULES_DIR/commands-index.mdc"
if command -v python3 >/dev/null 2>&1 && python3 -c 'import yaml' >/dev/null 2>&1; then
    index_body="$(python3 "$GEN_DOC" --compact 2>/dev/null || true)"
    if [[ -n "$index_body" ]]; then
        index_content="---
description: \"Manifest command index — categories + /command links; run /help for full descriptions.\"
alwaysApply: true
---

# Manifest Command Index

${index_body}

<!-- Auto-generated from .skillshare/skills/ via generate_commands_doc.py --compact -->
<!-- Regenerate: configs/claude/scripts/generate_cursor_rules.sh -->
"
        if [[ -f "$index_rule" ]]; then
            existing=$(cat "$index_rule"; printf x); existing="${existing%x}"
            if [[ "$existing" == "$index_content"$'\n' ]]; then
                log "Skip commands-index: unchanged"
                skipped=$((skipped + 1))
            elif $DRY_RUN; then
                echo "[DRY-RUN] Would update: $index_rule"
                updated=$((updated + 1))
            else
                echo "$index_content" > "$index_rule"
                log "Updated: $index_rule"
                updated=$((updated + 1))
            fi
        elif $DRY_RUN; then
            echo "[DRY-RUN] Would create: $index_rule"
            created=$((created + 1))
        else
            echo "$index_content" > "$index_rule"
            log "Created: $index_rule"
            created=$((created + 1))
        fi
    fi
else
    log "Skip commands-index.mdc: python3/pyyaml unavailable"
fi

echo "Cursor rules: $created created, $updated updated, $skipped unchanged"
