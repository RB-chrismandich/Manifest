#!/usr/bin/env bash
# plugin_drift_report.sh — detect hand-edits inside installed plugin bundles.
#
# Replaces apm_drift_report.sh's obligation, not its mechanism. Constitution
# Principle V.3 makes drift detection for owned paths a LIVE obligation, and it
# named apm_drift_report.sh as the implementation. Spec 674 Phase 5 retires that
# script, so the obligation needs a new subject or the control disappears with
# the tool — which is a silent weakening, not a migration.
#
# Plugins record only gitCommitSha + version, so a hand-edit inside
# ~/.claude/plugins/cache/.../SKILL.md is invisible to `claude plugin` itself,
# and reconcile.yml ignore-lists `plugins` outright. Nothing else would notice.
#
# For a DIRECTORY-source marketplace the reference copy is the repo, so drift is
# a plain tree comparison. That is the only case this handles, and it says so:
# a git- or registry-sourced bundle is reported UNCHECKED rather than clean,
# because "I could not look" must never render as "nothing is wrong".
set -euo pipefail

err() { printf 'plugin_drift_report.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: plugin_drift_report.sh [--repo DIR] [--quiet] [--help]

Compare installed Manifest plugin bundles against their repo source.

  --repo DIR   marketplace source (default: the repo this script lives in)
  --quiet      print only the verdict line
  --help       this text

Exit 0 = no drift; 1 = drift found; 2 = indeterminate (nothing checkable).
USAGE
    exit 0
fi

REPO=""
QUIET=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --quiet) QUIET=1 ;;
        --repo)
            shift
            REPO="${1:-}"
            ;;
        *)
            err "unknown argument: $1 (try --help)"
            exit 2
            ;;
    esac
    shift
done
[[ -n "$REPO" ]] || REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

CACHE="${CLAUDE_PLUGIN_CACHE:-$HOME/.claude/plugins/cache/manifest}"
if [[ ! -d "$CACHE" ]]; then
    echo "No Manifest bundles installed — nothing to check."
    exit 2
fi

drift=0
checked=0
while IFS= read -r installed; do
    # An update installs a NEW version dir and marks the old one .orphaned_at;
    # both stay on disk. Comparing every version dir reports the superseded copy
    # as drift forever — the same filter subagent_model_default.py needed.
    [[ -e "$installed/.orphaned_at" ]] && continue
    bundle="$(basename "$(dirname "$installed")")"
    src="$REPO/plugins/$bundle"
    if [[ ! -d "$src" ]]; then
        echo "UNCHECKED $bundle — no source at ${src#"$REPO"/} (not a directory-source bundle?)"
        continue
    fi
    checked=$((checked + 1))
    # -r compares recursively; -q reports only that files differ. Excludes are
    # build litter the install legitimately creates.
    if ! diff -qr -x '__pycache__' -x '*.pyc' -x '.DS_Store' \
        "$src" "$installed" > /tmp/.plugin_drift.$$ 2>&1; then
        drift=1
        [[ "$QUIET" -eq 1 ]] || sed "s|^|DRIFT     $bundle: |" /tmp/.plugin_drift.$$
    fi
    rm -f /tmp/.plugin_drift.$$
done < <(find "$CACHE" -mindepth 2 -maxdepth 2 -type d 2> /dev/null | sort)

if [[ "$checked" -eq 0 ]]; then
    echo "Indeterminate: no bundle could be compared against a source tree."
    exit 2
fi
if [[ "$drift" -eq 1 ]]; then
    echo ""
    echo "Installed bundles differ from their source. Plugin caches are build"
    echo "outputs — reinstall with 'claude plugin update <bundle>@manifest', and"
    echo "move any change you want to keep into plugins/<bundle>/."
    exit 1
fi
echo "No drift: $checked bundle(s) match their source tree."
