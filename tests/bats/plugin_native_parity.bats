#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
}

@test "capability matrix has no unverified or blank cells" {
  run uv run python "$REPO_ROOT/tools/render_plugin_capability_matrix.py" --check \
    --inspection "$REPO_ROOT/tests/fixtures/plugin_capability_inspection.json"
  [ "$status" -eq 0 ]
}

@test "all production adapters complete response-driven isolated-home lifecycles" {
  run uv run pytest "$REPO_ROOT/tests/python/manifest_agent/test_native_adapter_integration.py" -q
  [ "$status" -eq 0 ]
}
