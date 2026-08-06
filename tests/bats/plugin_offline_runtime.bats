#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
}

@test "bundle runtime path gate accepts local bundles without network tooling" {
  local fixture_bin
  fixture_bin="$(mktemp -d "${BATS_TMPDIR:-/tmp}/manifest-offline.XXXXXX")"
  trap 'rm -rf "$fixture_bin"' RETURN
  for command in curl npm npx uv uvx; do
    printf '#!/usr/bin/env sh\necho network disabled >&2\nexit 127\n' > "$fixture_bin/$command"
    chmod +x "$fixture_bin/$command"
  done
  run env PATH="$fixture_bin:/usr/bin:/bin" UV_NO_NETWORK=1 \
    "$REPO_ROOT/.venv/bin/python3" "$REPO_ROOT/tools/check_plugin_runtime_paths.py"
  [ "$status" -eq 0 ]
}
