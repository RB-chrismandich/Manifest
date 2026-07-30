#!/usr/bin/env bash
# manifest-cli-wrapper: installed to ~/.local/bin/manifest by bootstrap.sh.
# This marker is the ownership test — install_manifest_wrapper() backs up any
# same-named file that lacks it instead of overwriting someone else's CLI, so do
# not remove it. Local edits here are overwritten on the next bootstrap.
# help-coverage: exempt — thin exec wrapper; argv IS the wrapped command, so --help
# is the home runtime's, not this script's. Gating it would make the suite pass or
# fail on whether ~/.claude/.venv happens to exist (green locally, red in CI).
set -euo pipefail

# execfail: without it a failed `exec` kills this shell with bash's own cryptic
# message ("bad interpreter", "Bad CPU type in executable" after an Intel→ARM
# migration). With it, exec returns and we own the diagnostic.
shopt -s execfail

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

# HOME is absent in launchd/cron/systemd and some container contexts. Bash tilde
# expansion falls back to the passwd entry when HOME is unset, so `cd ~` still
# resolves the real home; only a truly unresolvable home is fatal.
home_dir="${HOME:-}"
if [[ -z $home_dir ]]; then
    home_dir="$(cd ~ 2> /dev/null && pwd)" || home_dir=""
fi
if [[ -z $home_dir ]]; then
    err "cannot locate your home directory (HOME is unset) — set HOME, or set MANIFEST_HOME to the runtime root"
    exit 78 # EX_CONFIG
fi

# MANIFEST_HOME relocates the whole runtime (non-standard installs, CI fixtures).
RUNTIME_ROOT="${MANIFEST_HOME:-$home_dir/.claude}"
VENV_BIN="$RUNTIME_ROOT/.venv/bin"
VENV_MANIFEST="$VENV_BIN/manifest"

# Name the clone bootstrap actually deployed from, so remediation is a command the
# user can paste. The state-root stamp is checked first because it survives a
# deleted ~/.claude — the exact case where the hint matters most. Both lookups are
# best-effort: an unstamped install falls back to the generic form.
bootstrap_hint() {
    local stamp clone
    for stamp in \
        "${MANIFEST_STATE_ROOT:-$home_dir/.manifest}/runtime.env" \
        "$RUNTIME_ROOT/config/deploy_stamp"; do
        [[ -r $stamp ]] || continue
        clone="$(sed -n 's/^clone_path=//p' "$stamp" 2> /dev/null | tail -n 1)" || clone=""
        if [[ -n $clone && -d $clone ]]; then
            printf '%s/bootstrap.sh' "$clone"
            return 0
        fi
    done
    printf './bootstrap.sh'
}

# Checks are ordered by what the exec path actually needs, so the first failure
# names the real cause. uv is deliberately NOT checked: this wrapper execs the
# venv's console script directly and never invokes uv, so gating on it turned
# every minimal-PATH context (launchd, cron, hooks with PATH=/usr/bin:/bin) into
# a hard failure against a perfectly healthy runtime. uv belongs to bootstrap and
# is reported by `manifest doctor`.
if [[ ! -d $RUNTIME_ROOT ]]; then
    err "home runtime not installed — $RUNTIME_ROOT is missing; re-run $(bootstrap_hint)"
    exit 1
fi
if [[ ! -e $VENV_MANIFEST ]]; then
    if [[ ! -d $RUNTIME_ROOT/.venv ]]; then
        err "home runtime not installed — no venv at $RUNTIME_ROOT/.venv; re-run $(bootstrap_hint)"
    else
        err "home runtime incomplete — $VENV_MANIFEST is missing (interrupted sync?); re-run $(bootstrap_hint)"
    fi
    exit 1
fi
if [[ ! -x $VENV_MANIFEST ]]; then
    err "home runtime not executable — $VENV_MANIFEST lost its executable bit; re-run $(bootstrap_hint)"
    exit 1
fi
# Validate the console script's own shebang rather than a guessed interpreter
# path. This catches every way a venv stops being runnable while its files are
# still present: the base Python was upgraded away, the tree was copied from
# another machine or home directory (absolute shebang now stale), or the script
# was truncated by a full disk. Left to exec, all three produce bash's
# "bad interpreter"/"Undefined error: 0" noise — and a truncated script is worse,
# because ENOEXEC makes bash reinterpret it as a shell script.
shebang=""
read -r shebang < "$VENV_MANIFEST" 2> /dev/null || shebang=""
if [[ $shebang != '#!'* ]]; then
    err "home runtime is corrupt — $VENV_MANIFEST has no interpreter line; re-run $(bootstrap_hint)"
    exit 1
fi
interp="${shebang#\#!}"
interp="${interp%%[[:space:]]*}"
# `#!/usr/bin/env python3` delegates interpreter lookup to env; check the venv's
# own interpreter in that case, which is what env would resolve to on PATH.
if [[ ${interp##*/} == env ]]; then
    interp="$VENV_BIN/python3"
    [[ -x $interp ]] || interp="$VENV_BIN/python"
fi
if [[ ! -x $interp ]]; then
    err "home runtime is broken — its interpreter ($interp) is missing or unusable (Python upgraded, or the venv was copied from another home); re-run $(bootstrap_hint)"
    exit 1
fi

# The `||` branch runs only when exec itself failed (execfail above): wrong
# architecture after a machine migration, noexec mount, truncated binary. It also
# keeps `set -e` from exiting on exec's status before the diagnostic is printed.
exec "$VENV_MANIFEST" "$@" || {
    err "could not start the home runtime ($VENV_MANIFEST) — re-run $(bootstrap_hint)"
    exit 1
}
