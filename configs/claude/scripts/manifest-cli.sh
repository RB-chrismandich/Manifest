#!/usr/bin/env bash
set -euo pipefail

err() { printf 'manifest: %s\n' "$*" >&2; }

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV_BIN="${HOME}/.local/bin/uv"
else
  err "uv not found — re-run ./bootstrap.sh"
  exit 1
fi

VENV_MANIFEST="${HOME}/.claude/.venv/bin/manifest"
if [[ ! -x "$VENV_MANIFEST" ]]; then
  err "home runtime not installed — re-run ./bootstrap.sh"
  exit 1
fi

exec "$VENV_MANIFEST" "$@"
