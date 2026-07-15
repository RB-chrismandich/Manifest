#!/usr/bin/env bash
set -euo pipefail

err() { printf 'manifest: %s\n' "$*" >&2; }

if ! command -v uv >/dev/null 2>&1 && [[ ! -x "${HOME}/.local/bin/uv" ]]; then
  err "uv not found — re-run ./bootstrap.sh"
  exit 1
fi

VENV_MANIFEST="${HOME}/.claude/.venv/bin/manifest"
if [[ ! -x "$VENV_MANIFEST" ]]; then
  err "home runtime not installed — re-run ./bootstrap.sh"
  exit 1
fi

exec "$VENV_MANIFEST" "$@"
