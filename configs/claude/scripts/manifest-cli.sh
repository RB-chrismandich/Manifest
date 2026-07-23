#!/usr/bin/env bash
set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "manifest: $*" >&2; else printf '%s\n' "manifest: $*" >&2; fi; }

if ! command -v uv > /dev/null 2>&1 && [[ ! -x "${HOME}/.local/bin/uv" ]]; then
    err "uv not found — re-run ./bootstrap.sh"
    exit 1
fi

VENV_MANIFEST="${HOME}/.claude/.venv/bin/manifest"
if [[ ! -x "$VENV_MANIFEST" ]]; then
    err "home runtime not installed — re-run ./bootstrap.sh"
    exit 1
fi

exec "$VENV_MANIFEST" "$@"
