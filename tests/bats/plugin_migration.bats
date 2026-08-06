#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
}

@test "legacy inventory renders deterministically" {
  run uv run python "$REPO_ROOT/tools/render_capability_inventory.py" --check
  [ "$status" -eq 0 ]
}

@test "migration inventory rejects forbidden shared runtime destinations" {
  run grep -nE 'manifest-core.*bootstrap.*shared-plugin' \
    "$REPO_ROOT/src/manifest_agent/migration.py"
  [ "$status" -eq 0 ]
}
