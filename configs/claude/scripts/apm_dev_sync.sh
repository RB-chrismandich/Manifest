#!/usr/bin/env bash
# T055/FR-032: the publish-free local development loop.
#
# A contributor edits a skill under .apm/skills/ and sees it in their own HOME
# without publishing anything to a git host or registry. This is the replacement
# for `sync-skills` under APM ownership, and it lands BEFORE that writer is
# gated (T014/T015) so gating removes a path rather than the only path.
#
# What this buys over `sync-skills`: apm records what it deployed in a lockfile,
# so a skill DELETED from .apm/skills/ is REMOVED from the home on the next run.
# `sync-skills` copies, and a copy cannot un-copy — deleted skills linger until
# someone notices. Verified on the real 108-skill tree: edit propagates,
# addition deploys, deletion cleans up.
#
# Why it stages instead of installing the checkout directly: `apm install <path>`
# copies the whole package root and HARD-FAILS on any symlink resolving outside
# it (PathTraversalError — a deliberate guard, not a bug). The repo has one:
# configs/claude/.venv/bin/python, created by the ordinary `uv sync` dev setup.
# Rather than weaken the guard or ask contributors to delete their venv, the loop
# assembles a clean staging package containing only apm.yml + .apm/skills.
#
# The staging directory basename is STABLE ("manifest-skills") on purpose: apm
# keys local package ownership off it (`_local/manifest-skills` in the
# lockfile). A per-run mktemp name would register a brand-new package every run,
# and deletion cleanup — the whole reason to prefer this over sync-skills —
# would silently stop working.
set -euo pipefail

err() { printf 'apm-dev-sync: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: apm-dev-sync [--target LIST]

Deploy .apm/skills/ into your own HOME via apm — no publish, no registry.
The local development loop for skill authoring. Unlike sync-skills, a skill
deleted from .apm/skills/ is also removed from your home.

  --target LIST   Comma-separated apm targets (default: claude).
                  Other harnesses inherit via the ~/.claude symlink fan-out.

Requires apm (./bootstrap.sh --enable-apm) and MANIFEST_ROOT, or run it
from inside a Manifest checkout.
USAGE
    exit 0
fi

TARGETS="claude"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            TARGETS="${2:-}"
            [[ -n "$TARGETS" ]] || {
                err "--target requires a value"
                exit 2
            }
            shift 2
            ;;
        *)
            err "unknown argument: $1 (see --help)"
            exit 2
            ;;
    esac
done

# MANIFEST_ROOT is exported into the shell profile by bootstrap.sh. Fall back to
# the enclosing checkout so the loop also works for someone who just cloned and
# has not bootstrapped yet.
#
# ROOT_SOURCE is tracked so a wrong root is a diagnosable error rather than a
# puzzle: with several Manifest clones on one machine (or a profile MANIFEST_ROOT
# left over from an older clone) the resolved root can be a real repo that simply
# has no .apm/skills, and "is this a Manifest checkout?" is then the least useful
# question to ask — the caller needs to know WHICH path was used and how to
# override it. Observed in the field on a machine with two clones.
ROOT="${MANIFEST_ROOT:-}"
ROOT_SOURCE="MANIFEST_ROOT"
if [[ -z "$ROOT" ]] && git rev-parse --show-toplevel > /dev/null 2>&1; then
    ROOT="$(git rev-parse --show-toplevel)"
    ROOT_SOURCE="the git checkout enclosing $PWD"
fi
[[ -n "$ROOT" ]] || {
    err "MANIFEST_ROOT not set and not inside a git checkout. Re-run bootstrap.sh,"
    err "or: MANIFEST_ROOT=/path/to/Manifest apm-dev-sync"
    exit 1
}
[[ -d "$ROOT/.apm/skills" ]] || {
    err "no .apm/skills/ under '$ROOT' (resolved from $ROOT_SOURCE)"
    if [[ -d "$ROOT/.skillshare/skills" ]]; then
        err "that checkout predates the .apm migration (it still has .skillshare/skills) — update it,"
        err "or point at a current checkout: MANIFEST_ROOT=/path/to/Manifest apm-dev-sync"
    else
        err "point at a Manifest checkout: MANIFEST_ROOT=/path/to/Manifest apm-dev-sync"
    fi
    exit 1
}

APM_BIN=""
if command -v apm > /dev/null 2>&1; then
    APM_BIN="apm"
elif [[ -x "$HOME/.local/bin/apm" ]]; then
    APM_BIN="$HOME/.local/bin/apm"
else
    err "apm not found. Install it with: ./bootstrap.sh --enable-apm"
    err "(apm is opt-in; its binary is checksum-verified and fails closed.)"
    exit 1
fi

STAGE_ROOT="${MANIFEST_APM_DEV_STAGE:-${TMPDIR:-/tmp}/manifest-apm-dev}"
STAGE="$STAGE_ROOT/manifest-skills"

# Rebuilt from scratch every run so the staging tree MIRRORS the source: a skill
# deleted from .apm/skills/ must not survive in staging, or apm would keep
# deploying it. Guarded because this is an rm -rf on an env-var-derived path —
# only ever the fixed 'manifest-skills' leaf, never STAGE_ROOT itself.
[[ "$(basename "$STAGE")" == "manifest-skills" ]] || {
    err "refusing to clear unexpected staging path: $STAGE"
    exit 1
}
rm -rf "$STAGE"
mkdir -p "$STAGE/.apm"
cp -R "$ROOT/.apm/skills" "$STAGE/.apm/skills"

# Generated, never committed. The real published package manifest is T018's;
# this one exists only to make the local install a valid apm package.
#
# targets: [claude] implements T013's arrangement, measured rather than assumed:
# T005 cell (i) recorded that apm PRESERVES a symlinked target directory instead
# of replacing it, so ~/.cursor/skills -> ~/.claude/skills and its siblings
# inherit this deploy. Naming the other harnesses would turn one shared tree into
# five independent copies free to drift — the outcome FR-033 exists to prevent.
cat > "$STAGE/apm.yml" << 'YML'
name: manifest-skills
version: 0.0.0
description: Manifest agent skills (generated development-scope package; unpublished)
targets:
  - claude
includes: auto
YML

echo "apm-dev-sync: staging $ROOT/.apm/skills -> $STAGE"
if ! (cd "$STAGE" && "$APM_BIN" install --global "$STAGE" --target "$TARGETS"); then
    err "apm install failed — nothing was deployed"
    exit 1
fi

# A silent no-op must not read as success: assert the home actually holds skills
# afterwards. An empty-vs-empty comparison would pass forever.
#
# Guarded deliberately. Under `set -euo pipefail`, `find` on a missing directory
# exits non-zero, pipefail propagates it through `wc`, and set -e kills the
# script *before* the diagnostic below — so the exact case this check exists to
# report would abort silently. Caught by its own test.
deployed=0
if [[ -d "$HOME/.claude/skills" ]]; then
    deployed="$(find "$HOME/.claude/skills" -name SKILL.md 2> /dev/null | wc -l | tr -d ' ')" || deployed=0
fi
if [[ "$deployed" == "0" ]]; then
    err "apm reported success but no SKILL.md landed in ~/.claude/skills — treating as failure"
    exit 1
fi
echo "apm-dev-sync: $deployed skill(s) deployed to ~/.claude/skills (no publish)"

# BEFORE the domain is gated, two other writers still own it. Both copy from the
# same .apm/skills source, so the bytes match and nothing is lost — but ownership
# is genuinely ambiguous in that window, and a contributor should be told rather
# than left to infer it from surprising behaviour.
#
# AFTER gating (SC-006 did this for `skills`) the same note is simply false:
# deploy_home_skills and sync-skills stand down, so telling someone that
# ./bootstrap.sh "also writes" the tree sends them to a command that will not
# refresh their skills at all. Ownership is a fact the registry already answers —
# so read it instead of hardcoding the migration's mid-state.
if [[ "${APM_DEV_SYNC_QUIET:-}" != "1" ]]; then
    _apm_lib=""
    for _cand in "$ROOT/configs/claude/scripts/apm_domains_lib.sh" \
        "$HOME/.claude/scripts/apm_domains_lib.sh"; do
        [[ -f "$_cand" ]] && {
            _apm_lib="$_cand"
            break
        }
    done
    # Absent registry (or absent library) means "APM owns nothing" — the same
    # fail-safe direction apm_owns_domain uses, so the note appears in exactly
    # the ungated case it describes.
    _gated=1
    if [[ -n "$_apm_lib" ]]; then
        # shellcheck disable=SC1090
        source "$_apm_lib"
        apm_owns_domain skills && _gated=0
    fi
    if [[ "$_gated" != "0" ]]; then
        echo ""
        echo "Note: ./bootstrap.sh and sync-skills also write ~/.claude/skills until"
        echo "      the 'skills' domain is gated in apm_domains.yml. They deploy the"
        echo "      same source, so re-running either is safe — but only apm-dev-sync"
        echo "      removes skills you deleted."
    fi
fi
