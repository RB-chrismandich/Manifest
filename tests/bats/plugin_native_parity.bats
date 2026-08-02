#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
}

@test "capability matrix has no unverified or blank cells" {
  run uv run python "$REPO_ROOT/tools/render_plugin_capability_matrix.py" --check
  [ "$status" -eq 0 ]
}
