#!/usr/bin/env bats
# Tests for configs/antigravity/ repo structure

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

@test "configs/antigravity/ exists" {
    [ -d "$REPO_ROOT/configs/antigravity" ]
}

@test "configs/antigravity/ symlinks all point to ../claude/ and resolve" {
    local ag_dir="$REPO_ROOT/configs/antigravity"
    for name in scripts config prompts skills .plans; do
        [ -L "$ag_dir/$name" ] || (echo "Missing symlink: $name" && false)
        local target
        target=$(readlink "$ag_dir/$name")
        assert_equal "$target" "../claude/$name"
        [ -e "$ag_dir/$name" ] || (echo "Dangling symlink: $name → $target" && false)
    done
}
