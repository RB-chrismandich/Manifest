#!/usr/bin/env bash
# apm_ungate_domain.sh — T053/FR-039/FR-019: hand a domain back to the legacy
# writer, mid-migration.
#
# Phase 2 deliberately leaves a domain with NO writer: the legacy pipeline has
# stood down and APM has not arrived yet. If the first APM deploy stalls — a
# failed publish, a rejected package, a late NO-GO — that domain is un-updatable
# by any mechanism until someone intervenes. This is that intervention, and it
# has to work in the middle of the migration, not only as part of a full
# rollback.
#
# Two steps, and the second is the one that is easy to forget:
#
#   1. UN-GATE — remove the domain from apm_domains.yml, so the legacy writer
#      stops standing down.
#   2. RECLAIM — delete the files APM already deployed for that domain.
#
# Without step 2 the domain ends up owned by NEITHER pipeline. The legacy writer
# only overwrites paths IT knows about; anything APM added that the legacy
# pipeline never writes survives as an orphan. That is precisely the
# untracked-hybrid state this whole feature exists to eliminate, so an un-gate
# that skips reclamation quietly recreates the problem it was called to fix.
#
# Reclamation is driven by the lockfile's own deployed_files inventory rather
# than by a glob, because the lockfile is the only record of what APM actually
# put there — a glob would also delete skills that other tools or plugins
# installed into the same directory.
#
# Dry-run by default, like every other destructive tool in this repo.
set -euo pipefail

err() { printf 'apm_ungate_domain.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: apm_ungate_domain.sh <domain> [--apply]

Return an APM-owned domain to the legacy deploy pipeline: remove it from
apm_domains.yml and delete the files APM deployed for it, so the domain has
exactly one owner again.

  <domain>   Domain name as it appears in apm_domains.yml (e.g. skills).
  --apply    Actually make the changes (default: preview only).

Re-run ./bootstrap.sh afterwards to repopulate the domain.
USAGE
    exit 0
fi

DOMAIN="${1:-}"
[[ -n "$DOMAIN" ]] || {
    err "a domain name is required (see --help)"
    exit 2
}
shift

APPLY=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=true
            shift
            ;;
        *)
            err "unknown argument: $1 (see --help)"
            exit 2
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ROOT="${MANIFEST_ROOT:-}"
if [[ -z "$ROOT" ]] && git -C "$SCRIPT_DIR" rev-parse --show-toplevel > /dev/null 2>&1; then
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
fi

REGISTRY="${MANIFEST_APM_DOMAINS:-$ROOT/configs/claude/config/apm_domains.yml}"
[[ -f "$REGISTRY" ]] || {
    err "domain registry not found: $REGISTRY"
    exit 1
}

LOCKFILE="${APM_LOCKFILE:-$HOME/.apm/apm.lock.yaml}"

if ! grep -qE "^[[:space:]]*-[[:space:]]*${DOMAIN}[[:space:]]*$|^domains:.*\b${DOMAIN}\b" "$REGISTRY"; then
    err "'$DOMAIN' is not listed in $REGISTRY — nothing to un-gate."
    exit 1
fi

# --- what APM deployed, per the lockfile ------------------------------------
# Empty inventory is reported, never silently treated as "nothing to reclaim":
# a lockfile that exists but lists no files is the signal that reclamation
# CANNOT be verified, which is a different situation from a clean one.
reclaim_list=""
if [[ -f "$LOCKFILE" ]]; then
    reclaim_list="$(awk '
        /^[[:space:]]*deployed_files:[[:space:]]*$/ { inlist = 1; next }
        inlist && /^[[:space:]]*-[[:space:]]*/ {
            item = $0
            sub(/^[[:space:]]*-[[:space:]]*/, "", item)
            print item
            next
        }
        inlist { inlist = 0 }
    ' "$LOCKFILE" || true)"
fi

echo "Domain:   $DOMAIN"
echo "Registry: $REGISTRY"
echo "Lockfile: $LOCKFILE"
echo ""

if [[ -z "$reclaim_list" ]]; then
    echo "APM-deployed files to reclaim: NONE FOUND"
    echo "  Either APM never deployed this domain, or the lockfile carries no"
    echo "  deployed-file inventory. If APM did deploy it, un-gating without"
    echo "  reclaiming leaves orphans owned by neither pipeline — check by hand"
    echo "  before trusting this as clean."
else
    echo "APM-deployed files to reclaim:"
    printf '  %s\n' $reclaim_list
fi
echo ""

if [[ "$APPLY" != true ]]; then
    echo "DRY RUN — nothing changed. Re-run with --apply to un-gate '$DOMAIN'."
    exit 0
fi

# --- 1. un-gate --------------------------------------------------------------
tmp="$(mktemp)"
awk -v want="$DOMAIN" '
    $0 ~ "^[[:space:]]*-[[:space:]]*" want "[[:space:]]*$" { next }
    { print }
' "$REGISTRY" > "$tmp"
mv "$tmp" "$REGISTRY"
echo "Un-gated: '$DOMAIN' removed from $REGISTRY"

# --- 2. reclaim --------------------------------------------------------------
# Paths in the lockfile are home-relative. Anything that escapes $HOME is
# refused rather than followed — a corrupted lockfile must not drive rm -rf.
reclaimed=0
for rel in $reclaim_list; do
    case "$rel" in
        /* | *..*)
            err "refusing to reclaim suspicious path: $rel"
            continue
            ;;
    esac
    target="$HOME/$rel"
    if [[ -e "$target" ]]; then
        rm -rf "$target"
        reclaimed=$((reclaimed + 1))
    fi
done
echo "Reclaimed: $reclaimed APM-deployed path(s) under \$HOME"

# --- 3. drop the lockfile's claim -------------------------------------------
# Reclaiming the files is not enough. apm_ownership_report.sh reads the LOCKFILE
# to decide whether APM still owns a domain, so a lockfile that still lists paths
# APM no longer has leaves the report stuck on DOUBLE-CLAIMED after a successful
# rollback — the un-gate would never reach the single-owner state it exists to
# restore. Found by running the tool, not by the unit tests, which asserted the
# writer side and never re-read the report.
if [[ -f "$LOCKFILE" ]] && command -v python3 > /dev/null 2>&1; then
    if python3 - "$LOCKFILE" "$DOMAIN" << 'PYEOF'; then
import sys

import yaml

path, domain = sys.argv[1], sys.argv[2]
prefix = f".claude/{domain}"
try:
    data = yaml.safe_load(open(path)) or {}
except Exception:
    sys.exit(1)


def strip(entry):
    for key in ("deployed_files", "deployed_file_hashes"):
        val = entry.get(key)
        if isinstance(val, list):
            entry[key] = [v for v in val if not str(v).startswith(prefix)]
        elif isinstance(val, dict):
            entry[key] = {k: v for k, v in val.items() if not str(k).startswith(prefix)}
    return entry


deps = data.get("dependencies")
if isinstance(deps, list):
    # Drop a dependency entirely once it produces nothing for any domain;
    # a husk with empty lists still reads as "apm deployed something here".
    kept = []
    for dep in deps:
        if not isinstance(dep, dict):
            kept.append(dep)
            continue
        strip(dep)
        if dep.get("deployed_files"):
            kept.append(dep)
    data["dependencies"] = kept

depl = data.get("deployments")
if isinstance(depl, list):
    data["deployments"] = [
        d for d in depl
        if not (isinstance(d, dict) and str(d.get("value", "")).startswith(prefix))
    ]

with open(path, "w") as f:
    yaml.safe_dump(data, f, default_flow_style=False, sort_keys=True)
PYEOF
        echo "Lockfile: dropped APM's claim on '$DOMAIN'"
    else
        err "could not update $LOCKFILE — apm may still appear to own '$DOMAIN'"
    fi
fi

echo ""
echo "'$DOMAIN' is back under the legacy pipeline and currently EMPTY."
echo "Run ./bootstrap.sh to repopulate it."
