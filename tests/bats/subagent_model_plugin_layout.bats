#!/usr/bin/env bats
# declared_model() must resolve a plugin's NAME in both installed layouts.
#
# There are two on-disk shapes for a plugin's agents:
#
#   marketplaces/<market>/plugins/<plugin>/agents/<agent>.md   <- plugin at [-2]
#   cache/<market>/<plugin>/<version>/agents/<agent>.md        <- plugin at [-3]
#
# declared_model() derived the plugin name from parts[-2] for both, so under the
# CACHE shape it used the VERSION string as the plugin name and built aliases
# like "0.3.0:facts-auditor". A qualified dispatch -- which is the only way
# Claude Code addresses a plugin agent -- therefore matched nothing.
#
# For a github-sourced plugin this is masked: the same plugin also exists under
# marketplaces/*/plugins/*, where [-2] is correct, so the pin is still found.
# It is NOT masked for a DIRECTORY-source marketplace, which has no marketplaces
# tree at all. Measured on this machine before the fix:
#
#   declared_model('part-forge:facts-auditor') -> None      (agent pins sonnet)
#   declared_model('facts-auditor')            -> 'sonnet'
#
# That matters beyond a missed pin. When declared_model returns None the hook
# treats the agent as unpinned and injects the default, so a plugin agent that
# deliberately asked for OPUS is silently downgraded -- the wrong-injection
# failure this hook's own docstring says it exists to avoid.
#
# It also matters for the cutover: T4.1 wires Manifest's nine bundles as a
# Directory-source marketplace (part-forge is configured exactly that way), so
# post-cutover every Manifest plugin agent lands in the unmasked case.

bats_require_minimum_version 1.5.0

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    SCRIPTS="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)"
    export HOME="$BATS_TEST_TMPDIR/home"
    mkdir -p "$HOME/.claude/agents"
    unset CLAUDE_PROJECT_DIR
}

# Build an agent definition under the cache layout (Directory-source shape:
# no marketplaces/ tree exists to mask a bad plugin-name derivation).
make_cache_agent() {
    local plugin="$1" version="$2" agent="$3" model="$4"
    local dir="$HOME/.claude/plugins/cache/$plugin/$plugin/$version/agents"
    mkdir -p "$dir"
    printf -- '---\nname: %s\nmodel: %s\n---\nbody\n' "$agent" "$model" > "$dir/$agent.md"
}

make_marketplace_agent() {
    local market="$1" plugin="$2" agent="$3" model="$4"
    local dir="$HOME/.claude/plugins/marketplaces/$market/plugins/$plugin/agents"
    mkdir -p "$dir"
    printf -- '---\nname: %s\nmodel: %s\n---\nbody\n' "$agent" "$model" > "$dir/$agent.md"
}

declared() {
    (cd "$SCRIPTS" && python3 -B -c "
import sys; sys.argv=['x']
import subagent_model_default as m
v = m.declared_model('$1')
print(v if v else 'NONE')
")
}

@test "cache layout: qualified dispatch resolves the plugin's pin" {
    make_cache_agent "part-forge" "0.3.0" "facts-auditor" "sonnet"
    run declared "part-forge:facts-auditor"
    assert_success
    assert_output "sonnet"
}

@test "cache layout: an OPUS pin is not lost (the wrong-injection case)" {
    # If declared_model returns NONE here the hook treats the agent as unpinned
    # and injects the default, silently downgrading a deliberate opus choice.
    make_cache_agent "part-forge" "0.3.0" "deep-reviewer" "opus"
    run declared "part-forge:deep-reviewer"
    assert_success
    assert_output "opus"
}

@test "cache layout: the VERSION string is not treated as the plugin name" {
    make_cache_agent "part-forge" "0.3.0" "facts-auditor" "sonnet"
    run declared "0.3.0:facts-auditor"
    assert_success
    assert_output "NONE"
}

@test "cache layout: an unqualified dispatch still resolves" {
    make_cache_agent "part-forge" "0.3.0" "facts-auditor" "sonnet"
    run declared "facts-auditor"
    assert_success
    assert_output "sonnet"
}

@test "cache layout: a literal 'unknown' version segment behaves the same" {
    # strict:false subset entries land under the literal segment 'unknown'.
    make_cache_agent "hookify" "unknown" "conversation-analyzer" "sonnet"
    run declared "hookify:conversation-analyzer"
    assert_success
    assert_output "sonnet"
}

@test "marketplace layout keeps working (no regression)" {
    make_marketplace_agent "claude-plugins-official" "pr-review-toolkit" "code-reviewer" "opus"
    run declared "pr-review-toolkit:code-reviewer"
    assert_success
    assert_output "opus"
}

@test "a qualified dispatch does not steal a HOME agent's pin" {
    # ~/.claude/agents/code-reviewer.md is a DIFFERENT agent from
    # someplugin:code-reviewer. Matching them would be a wrong injection.
    printf -- '---\nname: code-reviewer\nmodel: opus\n---\nbody\n' \
        > "$HOME/.claude/agents/code-reviewer.md"
    run declared "someplugin:code-reviewer"
    assert_success
    assert_output "NONE"
}

@test "home agents still resolve unqualified" {
    printf -- '---\nname: verifier\nmodel: opus\n---\nbody\n' \
        > "$HOME/.claude/agents/verifier.md"
    run declared "verifier"
    assert_success
    assert_output "opus"
}

# --- names that collide with the layout markers themselves -----------------
# The first fix derived the plugin name by INDEX, anchored on a path segment
# equal to the literal "plugins". A plugin whose own directory carries that
# name satisfied the marker test and short-circuited the cache branch, so the
# VERSION was returned again -- the exact defect the fix was written to remove,
# reintroduced by the fix. The name now comes from the glob that produced the
# directory, so no directory name can impersonate a layout marker.

@test "a plugin literally named 'plugins' still resolves" {
    make_cache_agent "plugins" "1.0.0" "collide" "opus"
    run declared "plugins:collide"
    assert_success
    assert_output "opus"
}

@test "a plugin literally named 'plugins' does not resolve by its version" {
    make_cache_agent "plugins" "1.0.0" "collide" "opus"
    run declared "1.0.0:collide"
    assert_success
    assert_output "NONE"
}

@test "a plugin literally named 'cache' still resolves" {
    make_cache_agent "cache" "2.1.0" "collide2" "opus"
    run declared "cache:collide2"
    assert_success
    assert_output "opus"
}

@test "a project dir named 'plugins' is not mistaken for a plugin root" {
    export CLAUDE_PROJECT_DIR="$BATS_TEST_TMPDIR/dev/plugins"
    mkdir -p "$CLAUDE_PROJECT_DIR/.claude/agents"
    printf -- '---\nname: local-helper\nmodel: opus\n---\nbody\n' \
        > "$CLAUDE_PROJECT_DIR/.claude/agents/local-helper.md"
    # A project agent is not owned by any plugin, so a qualified dispatch must
    # not reach it however the project directory happens to be named.
    run declared "plugins:local-helper"
    assert_success
    assert_output "NONE"
    run declared "local-helper"
    assert_success
    assert_output "opus"
}

# --- uninstalled versions must not win -------------------------------------
# `claude plugin uninstall` leaves the version tree on disk with an
# `.orphaned_at` marker rather than deleting it. The cache glob matched those
# too, and glob order is filesystem order, so an uninstalled version's pin
# could beat the live one non-deterministically. Live on this machine:
# pr-review-toolkit carries both an orphaned tree and a live one.

@test "an orphaned plugin version is ignored in favour of the live one" {
    make_cache_agent "part-forge" "0.1.0" "facts-auditor" "opus"
    touch "$HOME/.claude/plugins/cache/part-forge/part-forge/0.1.0/.orphaned_at"
    make_cache_agent "part-forge" "0.3.0" "facts-auditor" "sonnet"
    run declared "part-forge:facts-auditor"
    assert_success
    assert_output "sonnet"
}

@test "an agent surviving only in an orphaned version is not resolved" {
    make_cache_agent "part-forge" "0.1.0" "retired-agent" "opus"
    touch "$HOME/.claude/plugins/cache/part-forge/part-forge/0.1.0/.orphaned_at"
    run declared "part-forge:retired-agent"
    assert_success
    assert_output "NONE"
}

@test "root order is deterministic across runs" {
    make_cache_agent "part-forge" "0.1.0" "dup" "opus"
    make_cache_agent "part-forge" "0.3.0" "dup" "haiku"
    local first second
    first="$(declared 'part-forge:dup')"
    second="$(declared 'part-forge:dup')"
    [ "$first" = "$second" ]
}

# --- the installed set is the authority ------------------------------------
# Skipping `.orphaned_at` removed uninstalled versions from the CACHE, but two
# holes survived it, both found by adversarial audit and both dormant here:
#
#   1. Marketplace roots carry no orphan marker and are searched FIRST, so a
#      plugin whose cache versions were all uninstalled still resurrected its
#      pin from `marketplaces/<market>/plugins/<plugin>/agents`.
#   2. With two LIVE versions, sorted() picks the lexicographically first --
#      0.1.0 beats 0.3.0 -- so the OLDER pin won during an upgrade window. The
#      determinism test asserted only that two calls agree, never which wins.
#
# installed_plugins.json records the exact `installPath` Claude Code loads, so
# it settles both: a root counts only if the loader would actually load it.

write_installed() {
    local path="$HOME/.claude/plugins/installed_plugins.json"
    mkdir -p "$(dirname "$path")"
    printf '%s\n' "$1" > "$path"
}

@test "the installed version's pin wins over an older live version" {
    make_cache_agent "part-forge" "0.1.0" "dup" "opus"
    make_cache_agent "part-forge" "0.3.0" "dup" "haiku"
    write_installed "{\"version\":2,\"plugins\":{\"part-forge@part-forge\":[{\"scope\":\"user\",\"version\":\"0.3.0\",\"installPath\":\"$HOME/.claude/plugins/cache/part-forge/part-forge/0.3.0\"}]}}"

    run declared "part-forge:dup"
    assert_success
    assert_output "haiku"
}

@test "an uninstalled plugin does not resurrect its pin from the marketplace tree" {
    make_cache_agent "part-forge" "0.1.0" "ghost" "opus"
    touch "$HOME/.claude/plugins/cache/part-forge/part-forge/0.1.0/.orphaned_at"
    make_marketplace_agent "part-forge" "part-forge" "ghost" "opus"
    write_installed '{"version":2,"plugins":{}}'

    run declared "part-forge:ghost"
    assert_success
    assert_output "NONE"
}

@test "an installed plugin still resolves through its marketplace tree" {
    make_marketplace_agent "claude-plugins-official" "pr-review-toolkit" "code-reviewer" "opus"
    write_installed "{\"version\":2,\"plugins\":{\"pr-review-toolkit@claude-plugins-official\":[{\"scope\":\"user\",\"version\":\"1.0.0\",\"installPath\":\"$HOME/.claude/plugins/cache/claude-plugins-official/pr-review-toolkit/1.0.0\"}]}}"

    run declared "pr-review-toolkit:code-reviewer"
    assert_success
    assert_output "opus"
}

@test "a missing installed_plugins.json falls back, it does not blank the catalog" {
    # Fail-open: a hook that resolves nothing because one JSON file is absent
    # would silently stop honouring every pin on the machine.
    make_cache_agent "part-forge" "0.3.0" "facts-auditor" "sonnet"
    run declared "part-forge:facts-auditor"
    assert_success
    assert_output "sonnet"
}

@test "a malformed installed_plugins.json falls back rather than failing shut" {
    make_cache_agent "part-forge" "0.3.0" "facts-auditor" "sonnet"
    write_installed 'NOT JSON AT ALL {{{'
    run declared "part-forge:facts-auditor"
    assert_success
    assert_output "sonnet"
}

@test "an agent with no model pin returns NONE" {
    make_cache_agent "part-forge" "0.3.0" "plain" "sonnet"
    local dir="$HOME/.claude/plugins/cache/part-forge/part-forge/0.3.0/agents"
    printf -- '---\nname: plain\ndescription: no model\n---\nbody\n' > "$dir/plain.md"
    run declared "part-forge:plain"
    assert_success
    assert_output "NONE"
}
