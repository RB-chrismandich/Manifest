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

echo ""
echo "'$DOMAIN' is back under the legacy pipeline and currently EMPTY."
echo "Run ./bootstrap.sh to repopulate it."
