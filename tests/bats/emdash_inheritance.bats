#!/usr/bin/env bats
# Tests for configs/claude/scripts/emdash_inherit_check.sh — the emdash
# config-inheritance probe.
#
# Drives the probe (--json) against the synthetic launch-env fixture in
# tests/bats/fixtures/emdash/ (a fake $HOME/.claude deploy + a fake worktree
# checkout + the two .emdash-merged settings variants). Asserts the full
# inheritance surface (D1-D6) resolves, the emdash hook-merge preserves the
# HOME-side Manifest hooks and does not corrupt the worktree permissions, a
# missing home deploy BLOCKS (exit 2), and that emdash's injected PTY env
# (EMDASH_HOOK_PORT/EMDASH_PTY_ID/EMDASH_HOOK_NONCE) does not degrade resolution.
#
# Contract: specs/483-emdash-support/contracts/inheritance-probe.md (T004).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PROBE="$REPO_ROOT/configs/claude/scripts/emdash_inherit_check.sh"
HOME_FIX="$REPO_ROOT/tests/bats/fixtures/emdash/home"
WT_FIX="$REPO_ROOT/tests/bats/fixtures/emdash/worktree"

setup() {
    command -v python3 > /dev/null 2>&1 || skip "python3 not installed"
    # emdash's PTY injects these when it launches the agent (data-model E3).
    # Exported for every probe run so the fixture faithfully reproduces the
    # launch env; the non-degradation guarantee is asserted explicitly below.
    export EMDASH_HOOK_PORT=53517
    export EMDASH_PTY_ID="pty-483-abc"
    export EMDASH_HOOK_NONCE="nonce-deadbeef"
}

# --- JSON field getters (parse the probe's --json report) --------------------
verdict()    { python3 -c 'import json,sys;print(json.load(sys.stdin)["verdict"])'; }
dim_status() { python3 -c "import json,sys;print(json.load(sys.stdin)['dimensions']['$1']['status'])"; }
coex()       { python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin)['coexistence']['$1']))"; }

# --- CLI surface -------------------------------------------------------------

@test "--help exits 0 with usage before any config lookup" {
    run "$PROBE" --help
    assert_success
    assert_output --partial "Usage: emdash_inherit_check.sh"
}

# --- INHERITED: every dimension resolves against the fixture ------------------

@test "fixture launch-env yields verdict INHERITED with all dimensions PASS" {
    run "$PROBE" --json --home "$HOME_FIX" --worktree "$WT_FIX"
    assert_success   # exit 0 == INHERITED
    assert_equal "$(echo "$output" | verdict)" "INHERITED"
    for dim in skills subagents hooks mcp guide repo_guides; do
        assert_equal "$(echo "$output" | dim_status "$dim")" "PASS"
    done
}

# --- Coexistence: emdash hook-merge preserves Manifest config -----------------

@test "coexistence: Manifest hooks preserved + worktree permissions intact after emdash merge" {
    run "$PROBE" --json --home "$HOME_FIX" --worktree "$WT_FIX"
    assert_success
    # The .emdash-merged siblings are auto-detected as the simulated post-merge
    # state: HOME settings.json.emdash-merged (Manifest hooks + appended emdash
    # Stop hook) and worktree settings.local.json.emdash-merged (permissions +
    # appended emdash Stop hook).
    assert_equal "$(echo "$output" | coex emdash_hook_detected)" "true"
    assert_equal "$(echo "$output" | coex manifest_hooks_preserved)" "true"
    assert_equal "$(echo "$output" | coex worktree_permissions_intact)" "true"
}

# --- BLOCKED: home deploy missing --------------------------------------------

@test "missing home/.claude yields verdict BLOCKED and exit 2" {
    local no_home
    no_home="$(mktemp -d "${BATS_TMPDIR:-/tmp}/emdash_noconfig.XXXXXX")"
    run "$PROBE" --json --home "$no_home" --worktree "$WT_FIX"
    rm -rf "$no_home"
    assert_equal "$status" 2   # 2 == BLOCKED (home deploy not run)
    assert_equal "$(echo "$output" | verdict)" "BLOCKED"
}

# --- emdash PTY env does not degrade resolution ------------------------------

@test "EMDASH_HOOK_PORT/PTY_ID/HOOK_NONCE presence does not degrade resolution" {
    # Baseline: probe run WITHOUT emdash's injected env.
    run env -u EMDASH_HOOK_PORT -u EMDASH_PTY_ID -u EMDASH_HOOK_NONCE \
        "$PROBE" --json --home "$HOME_FIX" --worktree "$WT_FIX"
    assert_success
    local without_verdict="$(echo "$output" | verdict)"

    # With emdash's PTY env exported (as in setup): resolution must be identical.
    run "$PROBE" --json --home "$HOME_FIX" --worktree "$WT_FIX"
    assert_success
    local with_verdict="$(echo "$output" | verdict)"

    assert_equal "$with_verdict" "INHERITED"
    assert_equal "$with_verdict" "$without_verdict"
}
