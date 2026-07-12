#!/usr/bin/env bats
# Tests for configs/claude/scripts/generate_cursor_mcp.py (spec
# 2026-07-11-cursor-feature-parity WS-1) and its wiring into
# generate_cursor_rules.sh.
#
# generate_cursor_mcp.py derives REPO_ROOT from its own location
# (Path(__file__).resolve().parents[3]), so the hermetic seam is the script
# path: copying it (plus a fixture registry) into a sandbox that mirrors the
# configs/claude/{scripts,config}/... layout makes it operate entirely on
# sandbox files without any modification to the script itself.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    command -v python3 > /dev/null 2>&1 || skip "python3 not installed"
    python3 -c 'import yaml' 2> /dev/null || skip "PyYAML not installed"

    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/gen_cursor_mcp.XXXXXX")
    CONFIG_DIR="$SANDBOX/configs/claude/config"
    SCRIPTS_DIR="$SANDBOX/configs/claude/scripts"
    CURSOR_DIR="$SANDBOX/configs/cursor"
    REGISTRY="$CONFIG_DIR/mcp_servers.yml"
    OUTPUT="$CURSOR_DIR/mcp.json"
    GEN="$SCRIPTS_DIR/generate_cursor_mcp.py"

    mkdir -p "$CONFIG_DIR" "$SCRIPTS_DIR" "$CURSOR_DIR"
    cp "$REPO_ROOT/configs/claude/scripts/generate_cursor_mcp.py" "$GEN"
    chmod +x "$GEN"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# Helper: write a fixture registry with the given server names (each gets a
# distinct fake URL so per-server assertions can pin exact content).
make_registry() {
    {
        echo "mcp_servers:"
        for name in "$@"; do
            echo "  $name:"
            echo "    url: \"https://example.com/$name\""
            echo "    transport: \"http\""
        done
    } > "$REGISTRY"
}

# ── Generation ───────────────────────────────────────────────────────────────

@test "emits one mcpServers entry per url server, in registry order" {
    make_registry sentry context7 linear

    run "$GEN"
    assert_success
    assert_output --partial "3 servers"

    run cat "$OUTPUT"
    assert_output --partial '"sentry"'
    assert_output --partial '"url": "https://example.com/sentry"'
    assert_output --partial '"context7"'
    assert_output --partial '"linear"'

    # Registry order preserved: sentry key appears before context7, which
    # appears before linear.
    sentry_line=$(grep -n '"sentry"' "$OUTPUT" | cut -d: -f1)
    context7_line=$(grep -n '"context7"' "$OUTPUT" | cut -d: -f1)
    linear_line=$(grep -n '"linear"' "$OUTPUT" | cut -d: -f1)
    [ "$sentry_line" -lt "$context7_line" ]
    [ "$context7_line" -lt "$linear_line" ]
}

@test "output is valid JSON with the Cursor remote-MCP schema" {
    make_registry alpha beta
    run "$GEN"
    assert_success

    run python3 -c "
import json
d = json.load(open('$OUTPUT'))
assert set(d.keys()) == {'mcpServers'}
assert d['mcpServers']['alpha']['url'] == 'https://example.com/alpha'
assert d['mcpServers']['beta']['url'] == 'https://example.com/beta'
print('schema-ok')
"
    assert_success
    assert_output --partial "schema-ok"
}

@test "output ends with exactly one trailing newline" {
    make_registry alpha
    run "$GEN"
    assert_success
    # od shows the last byte; a single trailing \n means the file does not
    # end with \n\n and does end with \n.
    run bash -c "tail -c1 '$OUTPUT' | od -An -c | tr -d ' '"
    assert_output '\n'
}

@test "server entry without a url key is skipped, not emitted" {
    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  has-url:
    url: "https://example.com/has-url"
  no-url:
    transport: "stdio"
EOF
    run "$GEN"
    assert_success
    assert_output --partial "1 servers"

    run cat "$OUTPUT"
    assert_output --partial '"has-url"'
    refute_output --partial '"no-url"'
}

# ── Idempotence / change detection ──────────────────────────────────────────

@test "second run on an unchanged registry is a no-op (byte-identical)" {
    make_registry alpha beta
    "$GEN"
    before=$(shasum "$OUTPUT")

    run "$GEN"
    assert_success
    assert_output --partial "unchanged"
    assert_equal "$(shasum "$OUTPUT")" "$before"
}

@test "changed registry URL is reflected on regeneration" {
    make_registry alpha
    "$GEN"
    run cat "$OUTPUT"
    assert_output --partial "https://example.com/alpha"

    cat > "$REGISTRY" << 'EOF'
mcp_servers:
  alpha:
    url: "https://example.com/alpha-v2"
EOF
    run "$GEN"
    assert_success
    assert_output --partial "updated"

    run cat "$OUTPUT"
    assert_output --partial "https://example.com/alpha-v2"
}

# ── Dry run ──────────────────────────────────────────────────────────────────

@test "--dry-run on a missing output reports would-create and writes nothing" {
    make_registry alpha

    run "$GEN" --dry-run
    assert_success
    assert_output --partial "[DRY-RUN] Would create:"
    assert_output --partial "not written (--dry-run)"
    [ ! -e "$OUTPUT" ]
}

@test "--dry-run on a stale output reports would-update without modifying it" {
    make_registry alpha
    "$GEN"
    before=$(cat "$OUTPUT")

    make_registry alpha beta
    run "$GEN" --dry-run
    assert_success
    assert_output --partial "[DRY-RUN] Would update:"
    assert_equal "$(cat "$OUTPUT")" "$before"
}

@test "--dry-run on an already-current output reports unchanged, not would-update" {
    make_registry alpha
    "$GEN"

    run "$GEN" --dry-run
    assert_success
    refute_output --partial "[DRY-RUN]"
    assert_output --partial "unchanged"
}

# ── Errors ───────────────────────────────────────────────────────────────────

@test "missing registry file fails with a clear error" {
    rm -f "$REGISTRY"
    run "$GEN"
    assert_failure
    assert_output --partial "not found"
}

# ── Wiring into generate_cursor_rules.sh ────────────────────────────────────

@test "generate_cursor_rules.sh invokes the mcp generator when pyyaml is available" {
    SKILLS_DIR="$SANDBOX/configs/claude/skills"
    RULES_DIR="$SANDBOX/configs/cursor/rules"
    mkdir -p "$SKILLS_DIR" "$RULES_DIR"
    RULES_GEN="$SCRIPTS_DIR/generate_cursor_rules.sh"
    cp "$REPO_ROOT/configs/claude/scripts/generate_cursor_rules.sh" "$RULES_GEN"
    chmod +x "$RULES_GEN"
    make_registry alpha beta

    # generate_cursor_rules.sh also regenerates configs/cursor/agents/*.md
    # (spec 2026-07-11 cursor-feature-parity WS-5); stage the generator + a
    # minimal fixture source agent so the sandbox mirrors the real layout.
    AGENTS_DIR="$SANDBOX/configs/claude/agents"
    mkdir -p "$AGENTS_DIR"
    cp "$REPO_ROOT/configs/claude/scripts/generate_cursor_agents.py" "$SCRIPTS_DIR/generate_cursor_agents.py"
    chmod +x "$SCRIPTS_DIR/generate_cursor_agents.py"
    cat > "$AGENTS_DIR/fixture-agent.md" << 'EOF'
---
name: fixture-agent
description: "Fixture agent for generate_cursor_rules.sh sandbox tests."
model: haiku
effort: low
---

Fixture body.
EOF

    run "$RULES_GEN"
    assert_success
    assert_output --partial "Cursor mcp.json:"
    [ -f "$OUTPUT" ]
    run cat "$OUTPUT"
    assert_output --partial '"alpha"'
    assert_output --partial '"beta"'
}

# ── Real repo (read-only-ish guarded check) ─────────────────────────────────

@test "real repo: mcp.json contains all registry servers with matching URLs" {
    run python3 -c "
import yaml, json
registry = yaml.safe_load(open('$REPO_ROOT/configs/claude/config/mcp_servers.yml'))['mcp_servers']
cursor = json.load(open('$REPO_ROOT/configs/cursor/mcp.json'))['mcpServers']
expected = {name: cfg['url'] for name, cfg in registry.items() if 'url' in cfg}
missing = sorted(set(expected) - set(cursor))
mismatched = sorted(n for n in expected if n in cursor and cursor[n].get('url') != expected[n])
assert not missing, f'missing servers: {missing}'
assert not mismatched, f'mismatched urls: {mismatched}'
assert len(expected) == 9, f'expected 9 registry servers, found {len(expected)}'
print('real-repo-ok')
"
    assert_success
    assert_output --partial "real-repo-ok"
}

@test "real repo: regenerating mcp.json leaves the tree git-clean" {
    if ! git -C "$REPO_ROOT" diff --exit-code --quiet configs/cursor/mcp.json; then
        skip "configs/cursor/mcp.json has local modifications; skipping repo-level check"
    fi

    run python3 "$REPO_ROOT/configs/claude/scripts/generate_cursor_mcp.py"
    assert_success
    assert_output --partial "unchanged"

    git -C "$REPO_ROOT" diff --exit-code --quiet configs/cursor/mcp.json
}
