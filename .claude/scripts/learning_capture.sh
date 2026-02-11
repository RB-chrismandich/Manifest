#!/usr/bin/env bash
# learning_capture.sh - Structured learning ingestion and knowledge base updates
#
# Usage: learning_capture.sh <subcommand> [options]
#
# Subcommands:
#   add        Add a new learning entry to the knowledge base
#   query      Search existing entries by category, language, or tag
#   stats      Print summary statistics of the knowledge base
#   increment  Bump occurrences count for an existing entry by ID
#
# Examples:
#   learning_capture.sh add --title "Use ruff" --category tool_discovery \
#     --language python --description "Ruff replaces flake8+black+isort"
#   learning_capture.sh query --category antipattern --language python
#   learning_capture.sh stats
#   learning_capture.sh increment KB-003

set -euo pipefail

# --- Colors -----------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

# --- Knowledge base file location ------------------------------------
if [[ -f "${HOME}/.claude/config/knowledge_base.yml" ]]; then
    KNOWLEDGE_BASE_FILE="${HOME}/.claude/config/knowledge_base.yml"
elif [[ -f ".claude/config/knowledge_base.yml" ]]; then
    KNOWLEDGE_BASE_FILE=".claude/config/knowledge_base.yml"
else
    echo -e "${RED}Error: knowledge_base.yml not found in ~/.claude/config/ or .claude/config/${RESET}" >&2
    exit 1
fi

# --- Helper functions -------------------------------------------------

usage() {
    cat << 'USAGE'
learning_capture.sh - Structured learning ingestion and knowledge base updates

USAGE:
  learning_capture.sh <subcommand> [options]

SUBCOMMANDS:
  add          Add a new learning entry
  query        Search existing entries
  stats        Print summary statistics
  increment    Bump occurrences count for an entry

ADD OPTIONS:
  --title <text>        (required) Short title for the entry
  --category <cat>      (required) One of: pattern, antipattern, tool_discovery, config_insight
  --language <lang>     (required) Language: python, go, typescript, javascript, bash, terraform, yaml, general
  --description <text>  (required) Detailed description of the learning
  --tags <t1,t2,...>    (optional) Comma-separated tags
  --confidence <level>  (optional) high, medium, or low (default: medium)
  --source <text>       (optional) Source skill or context that produced this entry

QUERY OPTIONS:
  --category <cat>      Filter by category
  --language <lang>     Filter by language
  --tag <tag>           Filter by tag

INCREMENT:
  learning_capture.sh increment <ID>
    e.g. learning_capture.sh increment KB-003

EXAMPLES:
  learning_capture.sh add \
    --title "Use ruff instead of flake8" \
    --category tool_discovery \
    --language python \
    --description "Ruff is 10-100x faster and replaces multiple tools" \
    --tags "linting,performance" \
    --confidence high \
    --source refactor-python

  learning_capture.sh query --category antipattern --language python
  learning_capture.sh stats
  learning_capture.sh increment KB-001
USAGE
}

error_msg() {
    echo -e "${RED}Error: $1${RESET}" >&2
}

success_msg() {
    echo -e "${GREEN}$1${RESET}"
}

warn_msg() {
    echo -e "${YELLOW}$1${RESET}"
}

info_msg() {
    echo -e "${CYAN}$1${RESET}"
}

validate_category() {
    local cat="$1"
    case "$cat" in
        pattern | antipattern | tool_discovery | config_insight) return 0 ;;
        *)
            error_msg "Invalid category: $cat"
            echo "  Valid categories: pattern, antipattern, tool_discovery, config_insight" >&2
            return 1
            ;;
    esac
}

validate_confidence() {
    local conf="$1"
    case "$conf" in
        high | medium | low) return 0 ;;
        *)
            error_msg "Invalid confidence: $conf"
            echo "  Valid levels: high, medium, low" >&2
            return 1
            ;;
    esac
}

# --- Subcommand: add --------------------------------------------------

cmd_add() {
    local title="" category="" language="" description=""
    local tags="" confidence="medium" source=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --title)
                title="$2"
                shift 2
                ;;
            --category)
                category="$2"
                shift 2
                ;;
            --language)
                language="$2"
                shift 2
                ;;
            --description)
                description="$2"
                shift 2
                ;;
            --tags)
                tags="$2"
                shift 2
                ;;
            --confidence)
                confidence="$2"
                shift 2
                ;;
            --source)
                source="$2"
                shift 2
                ;;
            *)
                error_msg "Unknown option for add: $1"
                return 1
                ;;
        esac
    done

    # Validate required fields
    if [[ -z "$title" ]]; then
        error_msg "--title is required"
        return 1
    fi
    if [[ -z "$category" ]]; then
        error_msg "--category is required"
        return 1
    fi
    if [[ -z "$language" ]]; then
        error_msg "--language is required"
        return 1
    fi
    if [[ -z "$description" ]]; then
        error_msg "--description is required"
        return 1
    fi

    validate_category "$category" || return 1
    validate_confidence "$confidence" || return 1

    local today
    today=$(date +%Y-%m-%d)

    # Use python3 to safely read/write YAML and auto-generate ID
    local new_id
    new_id=$(
        python3 - "$KNOWLEDGE_BASE_FILE" "$title" "$category" "$language" \
            "$description" "$tags" "$confidence" "$source" "$today" << 'PYTHON'
import sys
import yaml

kb_file = sys.argv[1]
title = sys.argv[2]
category = sys.argv[3]
language = sys.argv[4]
description = sys.argv[5]
tags_str = sys.argv[6]
confidence = sys.argv[7]
source = sys.argv[8]
today = sys.argv[9]

# Read existing knowledge base
with open(kb_file, "r") as f:
    raw_content = f.read()

with open(kb_file, "r") as f:
    kb = yaml.safe_load(f) or {}

entries = kb.get("entries", []) or []

# Determine next ID: KB-NNN incrementing from existing entries
max_id = 0
for entry in entries:
    eid = entry.get("id", "KB-000")
    try:
        num = int(eid.split("-")[1])
        if num > max_id:
            max_id = num
    except (IndexError, ValueError):
        pass

new_id = f"KB-{max_id + 1:03d}"

# Build new entry
new_entry = {
    "id": new_id,
    "title": title,
    "category": category,
    "language": language,
    "description": description,
    "confidence": confidence,
    "created": today,
    "last_seen": today,
    "occurrences": 1,
}

if tags_str:
    new_entry["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]

if source:
    new_entry["source"] = source

entries.append(new_entry)
kb["entries"] = entries

# Preserve header comments by reading raw lines
with open(kb_file, "r") as f:
    raw_lines = f.readlines()

header_lines = []
for line in raw_lines:
    if line.startswith("#") or line.strip() == "":
        header_lines.append(line)
    else:
        break

with open(kb_file, "w") as f:
    for line in header_lines:
        f.write(line)
    yaml.dump(kb, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

print(new_id)
PYTHON
    )

    success_msg "Added entry ${new_id}: ${title}"
    info_msg "  Category: ${category} | Language: ${language} | Confidence: ${confidence}"
}

# --- Subcommand: query ------------------------------------------------

cmd_query() {
    local filter_category="" filter_language="" filter_tag=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --category)
                filter_category="$2"
                shift 2
                ;;
            --language)
                filter_language="$2"
                shift 2
                ;;
            --tag)
                filter_tag="$2"
                shift 2
                ;;
            *)
                error_msg "Unknown option for query: $1"
                return 1
                ;;
        esac
    done

    python3 - "$KNOWLEDGE_BASE_FILE" "$filter_category" "$filter_language" "$filter_tag" << 'PYTHON'
import sys
import yaml

kb_file = sys.argv[1]
filter_cat = sys.argv[2]
filter_lang = sys.argv[3]
filter_tag = sys.argv[4]

with open(kb_file, "r") as f:
    kb = yaml.safe_load(f) or {}

entries = kb.get("entries", []) or []

if not entries:
    print("No entries in knowledge base.")
    sys.exit(0)

matched = []
for entry in entries:
    if filter_cat and entry.get("category") != filter_cat:
        continue
    if filter_lang and entry.get("language") != filter_lang:
        continue
    if filter_tag:
        tags = entry.get("tags", []) or []
        if filter_tag not in tags:
            continue
    matched.append(entry)

if not matched:
    print("No matching entries found.")
    sys.exit(0)

print(f"Found {len(matched)} matching entries:\n")
for e in matched:
    print(f"  [{e.get('id', '?')}] {e.get('title', 'Untitled')}")
    print(f"    Category: {e.get('category', '?')} | Language: {e.get('language', '?')} | Confidence: {e.get('confidence', '?')}")
    desc = e.get("description", "")
    if desc:
        # Truncate long descriptions
        short = desc.strip().replace("\n", " ")[:120]
        if len(desc.strip()) > 120:
            short += "..."
        print(f"    Description: {short}")
    tags = e.get("tags", [])
    if tags:
        print(f"    Tags: {', '.join(tags)}")
    print(f"    Occurrences: {e.get('occurrences', 1)} | Last seen: {e.get('last_seen', '?')}")
    source = e.get("source")
    if source:
        print(f"    Source: {source}")
    print()
PYTHON
}

# --- Subcommand: stats ------------------------------------------------

cmd_stats() {
    python3 - "$KNOWLEDGE_BASE_FILE" << 'PYTHON'
import sys
import yaml
from collections import Counter

with open(sys.argv[1], "r") as f:
    kb = yaml.safe_load(f) or {}

entries = kb.get("entries", []) or []
total = len(entries)

if total == 0:
    print("Knowledge base is empty.")
    sys.exit(0)

categories = Counter(e.get("category", "unknown") for e in entries)
languages = Counter(e.get("language", "unknown") for e in entries)
confidences = Counter(e.get("confidence", "unknown") for e in entries)

print(f"Knowledge Base Statistics")
print(f"========================\n")
print(f"Total entries: {total}\n")

print("By Category:")
for cat, count in sorted(categories.items()):
    print(f"  {cat:20s} {count}")

print("\nBy Language:")
for lang, count in sorted(languages.items()):
    print(f"  {lang:20s} {count}")

print("\nBy Confidence:")
for conf, count in sorted(confidences.items()):
    print(f"  {conf:20s} {count}")
PYTHON
}

# --- Subcommand: increment --------------------------------------------

cmd_increment() {
    local entry_id="${1:-}"

    if [[ -z "$entry_id" ]]; then
        error_msg "Entry ID is required. Usage: learning_capture.sh increment KB-001"
        return 1
    fi

    local today
    today=$(date +%Y-%m-%d)

    local result
    result=$(
        python3 - "$KNOWLEDGE_BASE_FILE" "$entry_id" "$today" << 'PYTHON'
import sys
import yaml

kb_file = sys.argv[1]
entry_id = sys.argv[2]
today = sys.argv[3]

with open(kb_file, "r") as f:
    kb = yaml.safe_load(f) or {}

entries = kb.get("entries", []) or []
found = False

for entry in entries:
    if entry.get("id") == entry_id:
        entry["occurrences"] = entry.get("occurrences", 1) + 1
        entry["last_seen"] = today
        found = True
        print(f"OK:{entry['occurrences']}")
        break

if not found:
    print("NOT_FOUND")
    sys.exit(0)

kb["entries"] = entries

# Preserve header comments
with open(kb_file, "r") as f:
    raw_lines = f.readlines()

header_lines = []
for line in raw_lines:
    if line.startswith("#") or line.strip() == "":
        header_lines.append(line)
    else:
        break

with open(kb_file, "w") as f:
    for line in header_lines:
        f.write(line)
    yaml.dump(kb, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
PYTHON
    )

    if [[ "$result" == NOT_FOUND ]]; then
        error_msg "Entry ${entry_id} not found in knowledge base"
        return 1
    elif [[ "$result" == OK:* ]]; then
        local count="${result#OK:}"
        success_msg "Incremented ${entry_id}: occurrences now ${count}, last_seen updated to ${today}"
    else
        error_msg "Unexpected result from increment operation"
        return 1
    fi
}

# --- Main dispatch ----------------------------------------------------

main() {
    if [[ $# -lt 1 ]]; then
        usage
        exit 1
    fi

    local subcommand="$1"
    shift

    case "$subcommand" in
        add) cmd_add "$@" ;;
        query) cmd_query "$@" ;;
        stats) cmd_stats "$@" ;;
        increment) cmd_increment "$@" ;;
        help | --help | -h)
            usage
            exit 0
            ;;
        *)
            error_msg "Unknown subcommand: ${subcommand}"
            echo "" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"
