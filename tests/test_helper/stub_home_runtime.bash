# stub_home_manifest_runtime — fake ~/.claude/.venv for legacy .py shims in bats.
# Requires `uv sync --project configs/claude` (or pass a venv with manifest on PATH).
stub_home_manifest_runtime() {
    local repo="${1:-${REPO_ROOT:-}}"
    [[ -n "$repo" ]] || {
        echo "stub_home_manifest_runtime: REPO_ROOT unset" >&2
        return 1
    }
    local home="${HOME:?}"
    local venv_bin="$repo/configs/claude/.venv/bin"
    local manifest="$venv_bin/manifest"
    if [[ ! -x "$manifest" ]]; then
        echo "stub_home_manifest_runtime: missing $manifest — run: uv sync --project configs/claude" >&2
        return 1
    fi
    mkdir -p "$home/.claude/.venv/bin" "$home/.local/bin"
    ln -sf "$manifest" "$home/.claude/.venv/bin/manifest"
    ln -sf "$venv_bin/python" "$home/.claude/.venv/bin/python"
    printf '#!/bin/sh\nexit 0\n' > "$home/.local/bin/uv"
    chmod +x "$home/.local/bin/uv"
}
