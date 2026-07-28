#!/usr/bin/env bash
# help-coverage: exempt — thin exec wrapper; argv IS the wrapped command, so --help
# is the home runtime's, not this script's. Gating it would make the suite pass or
# fail on whether ~/.claude/.venv happens to exist (green locally, red in CI).
set -euo pipefail

# Red only on an interactive stderr, and never when NO_COLOR is set to a
# non-empty value (https://no-color.org). Piped/redirected output stays plain so
# callers parsing stderr do not have to strip escapes.
err() {
    if [[ -t 2 && -z ${NO_COLOR:-} ]]; then
        printf '\033[0;31m%s\033[0m\n' "manifest: $*" >&2
    else
        printf '%s\n' "manifest: $*" >&2
    fi
}

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
