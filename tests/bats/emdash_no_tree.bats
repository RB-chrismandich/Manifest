#!/usr/bin/env bats
# T016 (spec 483) — SC-006 / FR-008: emdash is an external harness, NOT a
# Manifest deploy target. This suite is the filesystem-checkable guarantee that
# the feature adds NO deploy tree and NO home config dir for emdash:
#
#   1. No `configs/emdash/` deploy-source tree exists in the repo.
#   2. The only committed per-repo emdash surface is `.emdash.json` (a FILE at
#      the root — the project config emdash itself reads), never a tree.
#   3. The bootstrap deploy layer references no emdash target, so a home deploy
#      can create no `~/.emdash/` — proven statically (the deploy code has zero
#      emdash references) AND by executing a real deploy path into a sandbox
#      HOME and confirming no `~/.emdash/` sibling appears.
#
# emdash inherits Manifest config transitively (real HOME + worktree checkout);
# see specs/483-emdash-support/ and docs/EMDASH.md.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

# ---- SC-006 / FR-008: no deploy-source tree ------------------------------- #

@test "no configs/emdash/ deploy tree exists (SC-006/FR-008)" {
    [ ! -d "$REPO_ROOT/configs/emdash" ] || {
        echo "FAIL: configs/emdash/ must not exist — emdash reads no deploy tree"
        false
    }
}

@test "no directory named emdash exists anywhere under configs/ (SC-006/FR-008)" {
    # The inheritance probe (configs/claude/scripts/emdash_inherit_check.sh) is a
    # FILE, not a tree; FR-008 forbids a deploy *directory*, which this asserts.
    local dirs
    dirs="$(find "$REPO_ROOT/configs" -type d -iname '*emdash*' 2> /dev/null)"
    [ -z "$dirs" ] || {
        echo "FAIL: emdash deploy directory found under configs/:"
        echo "$dirs"
        false
    }
}

@test ".emdash.json is a committed FILE — the only per-repo emdash surface, not a tree" {
    [ -f "$REPO_ROOT/.emdash.json" ] || {
        echo "FAIL: .emdash.json (the committed emdash project config) is missing"
        false
    }
    [ ! -d "$REPO_ROOT/.emdash" ] || {
        echo "FAIL: .emdash/ tree must not exist — the surface is the .emdash.json file"
        false
    }
}

# ---- FR-008: a home deploy creates no ~/.emdash/ -------------------------- #

@test "bootstrap deploy layer references no emdash target (home deploy creates no ~/.emdash/)" {
    # The ONLY way a home deploy could create ~/.emdash/ is if the deploy code
    # named it. Zero emdash references across bootstrap.sh + bootstrap/lib/*.sh
    # is therefore the deterministic guarantee that no such directory is created
    # (no deploy_emdash function, no EMDASH_TARGET_DIR, no ~/.emdash mkdir/link).
    local hits
    hits="$(grep -rniE 'emdash' "$REPO_ROOT/bootstrap.sh" "$REPO_ROOT"/bootstrap/lib/*.sh 2> /dev/null || true)"
    [ -z "$hits" ] || {
        echo "FAIL: bootstrap deploy layer references emdash — a home deploy could create ~/.emdash/:"
        echo "$hits"
        false
    }
}

@test "an executed home deploy path leaves no ~/.emdash/ directory" {
    # Execute a real deploy code path (deploy_antigravity_configs) against a
    # sandbox HOME and confirm it produces no ~/.emdash/ sibling — a runtime
    # complement to the static guarantee above.
    local sandbox
    sandbox="$(mktemp -d "${BATS_TMPDIR:-/tmp}/emdash_no_tree.XXXXXX")"
    export HOME="$sandbox/home"
    export TARGET_DIR="$HOME/.claude"
    export ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
    export ENABLE_ANTIGRAVITY=true
    mkdir -p "$HOME" "$TARGET_DIR"/scripts "$TARGET_DIR"/config \
        "$TARGET_DIR"/prompts "$TARGET_DIR"/.plans "$TARGET_DIR"/skills

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    run deploy_antigravity_configs
    assert_success
    [ ! -e "$HOME/.emdash" ] || {
        echo "FAIL: a home deploy created $HOME/.emdash — FR-008 forbids an emdash home config dir"
        rm -rf "$sandbox"
        false
    }
    rm -rf "$sandbox"
}
