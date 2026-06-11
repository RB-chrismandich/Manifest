#!/usr/bin/env bats
# Tests for configs/claude/scripts/learning_capture.sh
# Behavioral coverage: add, query, stats, increment, sync-docs, plus
# missing-knowledge_base.yml error path and YAML validity after mutation.
#
# Sandboxing: the script resolves the knowledge base from
# $HOME/.claude/config/knowledge_base.yml first, then ./.claude/config/.
# There is no explicit env/flag override, so every test points HOME at a
# mktemp sandbox and runs from inside it — the real KB is never touched.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/learning_capture.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/learning_capture.XXXXXX")
    export HOME="$SANDBOX"
    KB_FILE="$SANDBOX/.claude/config/knowledge_base.yml"
    mkdir -p "$SANDBOX/.claude/config"

    # Seed knowledge base with header comments + one entry
    cat > "$KB_FILE" << 'EOF'
# Knowledge Base - machine-readable source of truth
# Managed by learning_capture.sh

version: 1
entries:
  - id: KB-001
    title: "Use ruff instead of flake8"
    category: tool_discovery
    language: python
    description: "Ruff is faster and replaces flake8+black+isort"
    confidence: high
    created: "2026-01-01"
    last_seen: "2026-01-01"
    occurrences: 2
    tags:
      - linting
EOF

    cd "$SANDBOX"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Helper: assert KB file is still parseable YAML and print entry count
assert_kb_valid_yaml() {
    run python3 -c "
import yaml, sys
with open('$KB_FILE') as f:
    kb = yaml.safe_load(f)
assert isinstance(kb, dict), 'KB root is not a mapping'
print(len(kb.get('entries') or []))
"
    assert_success
}

# --- Help / usage ---

@test "shows usage with --help" {
    run bash "$SCRIPT" --help
    assert_success
    assert_output --partial "USAGE:"
    assert_output --partial "add"
    assert_output --partial "sync-docs"
}

@test "no arguments prints usage and exits non-zero" {
    run bash "$SCRIPT"
    assert_failure
    assert_output --partial "USAGE:"
}

@test "unknown subcommand fails with error" {
    run bash "$SCRIPT" bogus
    assert_failure
    assert_output --partial "Unknown subcommand: bogus"
}

# --- Missing knowledge base error path ---

@test "fails gracefully when knowledge_base.yml is missing" {
    rm -rf "$SANDBOX/.claude"
    run bash "$SCRIPT" stats
    assert_failure
    assert_output --partial "knowledge_base.yml not found"
}

# --- add ---

@test "add writes a new entry with auto-incremented ID" {
    run bash "$SCRIPT" add \
        --title "Avoid bare except" \
        --category antipattern \
        --language python \
        --description "Bare except clauses hide real errors" \
        --tags "exceptions,error-handling" \
        --confidence high \
        --source refactor-python
    assert_success
    assert_output --partial "Added entry KB-002: Avoid bare except"
    assert_output --partial "Category: antipattern | Language: python | Confidence: high"

    # Entry is present and parseable in the YAML file
    run python3 -c "
import yaml
kb = yaml.safe_load(open('$KB_FILE'))
e = [x for x in kb['entries'] if x['id'] == 'KB-002'][0]
assert e['title'] == 'Avoid bare except'
assert e['category'] == 'antipattern'
assert e['language'] == 'python'
assert e['confidence'] == 'high'
assert e['occurrences'] == 1
assert e['tags'] == ['exceptions', 'error-handling']
assert e['source'] == 'refactor-python'
print('entry ok')
"
    assert_success
    assert_output "entry ok"
}

@test "add preserves YAML header comments" {
    run bash "$SCRIPT" add \
        --title "T" --category pattern --language bash --description "D"
    assert_success
    run head -1 "$KB_FILE"
    assert_output "# Knowledge Base - machine-readable source of truth"
}

@test "KB file remains valid YAML after add mutation" {
    run bash "$SCRIPT" add \
        --title "Quote 'safe' entry: with colons & dashes" \
        --category config_insight \
        --language yaml \
        --description "Tricky chars: quotes ' \" and #hash should not corrupt YAML"
    assert_success
    assert_kb_valid_yaml
    assert_output "2"
}

@test "add fails when required --title is missing" {
    run bash "$SCRIPT" add --category pattern --language python --description "x"
    assert_failure
    assert_output --partial -- "--title is required"
}

@test "add rejects invalid category" {
    run bash "$SCRIPT" add \
        --title "T" --category nonsense --language python --description "D"
    assert_failure
    assert_output --partial "Invalid category: nonsense"
}

@test "add rejects invalid confidence" {
    run bash "$SCRIPT" add \
        --title "T" --category pattern --language python --description "D" \
        --confidence very-sure
    assert_failure
    assert_output --partial "Invalid confidence: very-sure"
}

# --- query ---

@test "query finds an added entry by category and language" {
    bash "$SCRIPT" add \
        --title "Prefer set -euo pipefail" \
        --category pattern \
        --language bash \
        --description "Strict mode catches unset vars and pipe failures" \
        --tags "strict-mode"
    run bash "$SCRIPT" query --category pattern --language bash
    assert_success
    assert_output --partial "Found 1 matching entries"
    assert_output --partial "[KB-002] Prefer set -euo pipefail"
    assert_output --partial "Tags: strict-mode"
}

@test "query filters by tag" {
    run bash "$SCRIPT" query --tag linting
    assert_success
    assert_output --partial "[KB-001] Use ruff instead of flake8"
}

@test "query reports no matches for unknown filter" {
    run bash "$SCRIPT" query --category pattern --language terraform
    assert_success
    assert_output --partial "No matching entries found."
}

@test "query --format llm emits markdown without ANSI colors" {
    run bash "$SCRIPT" query --language python --format llm
    assert_success
    assert_output --partial "## Known Issues: python"
    assert_output --partial "### Tool Discoveries"
    assert_output --partial "**KB-001** (high): Use ruff instead of flake8"
    refute_output --partial $'\033'
}

# --- stats ---

@test "stats reports totals by category, language, and confidence" {
    bash "$SCRIPT" add \
        --title "T2" --category antipattern --language python --description "D2" \
        --confidence low
    run bash "$SCRIPT" stats
    assert_success
    assert_output --partial "Total entries: 2"
    assert_output --partial "By Category:"
    assert_output --partial "antipattern"
    assert_output --partial "tool_discovery"
    assert_output --partial "By Language:"
    assert_output --partial "python"
    assert_output --partial "By Confidence:"
    assert_output --partial "high"
    assert_output --partial "low"
}

@test "stats reports empty knowledge base" {
    printf 'version: 1\nentries: []\n' > "$KB_FILE"
    run bash "$SCRIPT" stats
    assert_success
    assert_output --partial "Knowledge base is empty."
}

# --- increment ---

@test "increment bumps occurrences and updates last_seen" {
    local today
    today=$(date +%Y-%m-%d)
    run bash "$SCRIPT" increment KB-001
    assert_success
    assert_output --partial "Incremented KB-001: occurrences now 3, last_seen updated to $today"

    run python3 -c "
import yaml
kb = yaml.safe_load(open('$KB_FILE'))
e = [x for x in kb['entries'] if x['id'] == 'KB-001'][0]
print(e['occurrences'], e['last_seen'])
"
    assert_success
    assert_output "3 $today"
}

@test "KB file remains valid YAML after increment mutation" {
    bash "$SCRIPT" increment KB-001
    assert_kb_valid_yaml
    assert_output "1"
}

@test "increment fails for non-existent ID" {
    run bash "$SCRIPT" increment KB-999
    assert_failure
    assert_output --partial "Entry KB-999 not found in knowledge base"
}

@test "increment without ID fails with usage hint" {
    run bash "$SCRIPT" increment
    assert_failure
    assert_output --partial "Entry ID is required"
}

# --- sync-docs ---

@test "sync-docs regenerates docs/KNOWLEDGE_BASE.md from YAML" {
    mkdir -p "$SANDBOX/docs"
    run bash "$SCRIPT" sync-docs
    assert_success
    assert_output --partial "Regenerated"
    assert_output --partial "with 1 entries"
    assert_output --partial "docs/KNOWLEDGE_BASE.md regenerated from YAML source of truth"

    [ -f "$SANDBOX/docs/KNOWLEDGE_BASE.md" ]
    run cat "$SANDBOX/docs/KNOWLEDGE_BASE.md"
    assert_output --partial "# Knowledge Base"
    assert_output --partial "AUTO-GENERATED"
    assert_output --partial "Use ruff instead of flake8"
    assert_output --partial "KB-001"
}

@test "sync-docs fails outside a git repo when docs/ is absent" {
    # Sandbox is not a git repo and has no docs/ directory
    run bash "$SCRIPT" sync-docs
    assert_failure
    assert_output --partial "Cannot find docs/ directory"
}

@test "sync-docs reflects newly added entries" {
    mkdir -p "$SANDBOX/docs"
    bash "$SCRIPT" add \
        --title "Pin GitHub Actions by SHA" \
        --category pattern \
        --language yaml \
        --description "Tag refs are mutable; SHAs are not"
    run bash "$SCRIPT" sync-docs
    assert_success
    assert_output --partial "with 2 entries"
    run cat "$SANDBOX/docs/KNOWLEDGE_BASE.md"
    assert_output --partial "Pin GitHub Actions by SHA"
}
