#!/usr/bin/env bash
# deploy_reconcile.sh — Deploy Reconciliation Review (feature 368).
# Lists deployed units (skills/config) with no project source as KEEP/REMOVE.
# Preview by default; --remove moves REMOVE orphans to a recoverable backup.
# Read-only classification lives in reconcile_core.py; this wrapper owns the CLI,
# the confirm gate, and the destructive move. Contract: specs/368-…/contracts/reconcile-cli.md
set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "deploy-reconcile: $*" >&2; else printf '%s\n' "deploy-reconcile: $*" >&2; fi; }

usage() {
    cat << 'EOF'
Usage: deploy_reconcile.sh [--project DIR] [--remove] [--yes] [--json]
                           [--home DIR] [--root TAG] [--config PATH]
                           [--protect GLOB]... [--backup-dir DIR] [--help]

Reviews deployed assistant homes vs the project; lists KEEP/REMOVE orphans.
Default is a read-only preview. --remove moves REMOVE items to a recoverable
backup under ~/.manifest/reconcile-trash/<ts>/ (requires confirm or --yes).
--project is the repo root (or set MANIFEST_REPO). --json emits machine output.
EOF
}

# --- Parse args FIRST so --help works before any config/home/project lookup ---
DO_REMOVE=0
ASSUME_YES=0
AS_JSON=0
PROJECT=""
HOME_BASE=""
ROOT=""
CONFIG=""
BACKUP_DIR=""
PROTECT=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help | -h)
            usage
            exit 0
            ;;
        --remove)
            DO_REMOVE=1
            shift
            ;;
        --yes)
            ASSUME_YES=1
            shift
            ;;
        --json)
            AS_JSON=1
            shift
            ;;
        --project)
            PROJECT="${2:?--project needs a value}"
            shift 2
            ;;
        --home)
            HOME_BASE="${2:?--home needs a value}"
            shift 2
            ;;
        --root)
            ROOT="${2:?--root needs a value}"
            shift 2
            ;;
        --config)
            CONFIG="${2:?--config needs a value}"
            shift 2
            ;;
        --protect)
            PROTECT+=("${2:?--protect needs a value}")
            shift 2
            ;;
        --backup-dir)
            BACKUP_DIR="${2:?--backup-dir needs a value}"
            shift 2
            ;;
        *)
            err "unknown argument: $1"
            usage >&2
            exit 2
            ;;
    esac
done

[[ "${RECONCILE_ASSUME_YES:-0}" == "1" ]] && ASSUME_YES=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${MANIFEST_VENV_PY:-${HOME}/.claude/.venv/bin/python}"
CORE="$SCRIPT_DIR/reconcile_core.py"
[[ -f "$CORE" ]] || {
    err "missing core: $CORE"
    exit 1
}

# --- Build core args ---
core_args=(--format json)
[[ -n "$PROJECT" ]] && core_args+=(--project "$PROJECT")
[[ -n "$HOME_BASE" ]] && core_args+=(--home "$HOME_BASE")
[[ -n "$ROOT" ]] && core_args+=(--root "$ROOT")
[[ -n "$CONFIG" ]] && core_args+=(--config "$CONFIG")
for g in ${PROTECT[@]+"${PROTECT[@]}"}; do core_args+=(--protect "$g"); done

# --- Scan once (read-only). Core exit 2 = usage/unresolved project. ---
REPORT="$("$VENV_PY" "$CORE" "${core_args[@]}")" || {
    rc=$?
    exit "$rc"
}

# --- Preview (default) ---
if [[ "$DO_REMOVE" -eq 0 ]]; then
    if [[ "$AS_JSON" -eq 1 ]]; then
        printf '%s\n' "$REPORT"
    else
        printf '%s\n' "$REPORT" | "$VENV_PY" "$CORE" --from-json - --format human
    fi
    exit 0
fi

# --- Removal mode ---
# Show the preview the user is acting on, rendered from the SAME scan (no re-read,
# no TOCTOU). Note: this relies on reconcile_core.py's --from-json render contract.
printf '%s\n' "$REPORT" | "$VENV_PY" "$CORE" --from-json - --format human

# Extract REMOVE canonical paths from the captured report.
remove_paths="$(printf '%s\n' "$REPORT" | "$VENV_PY" -c \
    'import json,sys; d=json.load(sys.stdin); [print(i["canonical_path"]) for i in d["items"] if i["verdict"]=="REMOVE"]')"

if [[ -z "$remove_paths" ]]; then
    echo "deploy-reconcile: no REMOVE items. Nothing to remove."
    exit 0
fi

# Resolve trash root and refuse if it lands inside a managed root.
base="${HOME_BASE:-$HOME}"
state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
trash_root="${BACKUP_DIR:-${MANIFEST_RECONCILE_TRASH:-$state_root/reconcile-trash}}"
trash_abs="$("$VENV_PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$trash_root")"

# Fleet tag list — sourced from reconcile_core.py (agent_roster.yml-derived),
# not hardcoded here, so a 6th agent added to the registry needs no edit to
# either file (feature: derive agent fleet from agent_roster.yml).
fleet_tags_raw="$("$VENV_PY" "$CORE" --list-tags)" || {
    rc=$?
    err "failed to list agent fleet tags from $CORE"
    exit "$rc"
}
fleet_tags=()
while IFS= read -r t; do
    [[ -n "$t" ]] && fleet_tags+=("$t")
done <<< "$fleet_tags_raw"

for tag in ${fleet_tags[@]+"${fleet_tags[@]}"}; do
    rootp="$("$VENV_PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$base/.$tag")"
    case "$trash_abs/" in
        "$rootp"/*)
            err "--backup-dir resolves inside managed root $base/.$tag; refusing"
            exit 2
            ;;
    esac
done

RUN_TS="${MANIFEST_RECONCILE_TS:-$(date +%Y%m%d_%H%M%S)}"
trash_dir="$trash_root/$RUN_TS"
# Same-second collision guard.
if [[ -e "$trash_dir" ]]; then
    i=1
    while [[ -e "${trash_dir}_$i" ]]; do i=$((i + 1)); done
    trash_dir="${trash_dir}_$i"
fi

# Confirm gate (interactive /dev/tty unless --yes / RECONCILE_ASSUME_YES).
n="$(printf '%s\n' "$remove_paths" | grep -c .)"
if [[ "$ASSUME_YES" -ne 1 ]]; then
    echo "About to move $n REMOVE item(s) to:"
    echo "  $trash_dir/"
    ans=""
    if [[ -t 1 && -r /dev/tty ]]; then # only prompt with a real interactive terminal
        printf 'Proceed? [y/N] ' > /dev/tty
        read -r ans < /dev/tty || ans=""
    fi
    case "$ans" in
        y | Y | yes | YES) : ;;
        *)
            echo "deploy-reconcile: --remove requires confirmation. Nothing removed."
            echo "Re-run with --yes for non-interactive removal (or RECONCILE_ASSUME_YES=1)."
            exit 0
            ;;
    esac
fi

# restore.sh is (re)generated via an EXIT trap so a partial failure still leaves a
# usable recovery script for whatever was already moved (P-II review, Medium finding).
# It restores canonical paths first so secondary-home symlinks re-resolve.
write_restore_sh() {
    [[ -s "$manifest" ]] || return 0
    cat > "$trash_dir/restore.sh" << 'RST'
#!/usr/bin/env bash
# Restore items moved by deploy-reconcile. Run from anywhere.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while IFS=$'\t' read -r src dest; do
  [[ -z "$src" ]] && continue
  mkdir -p "$(dirname "$src")"
  mv "$dest" "$src" && echo "restored: $src"
done < "$here/removed.tsv"
RST
    chmod 700 "$trash_dir/restore.sh"
}

base_real="$("$VENV_PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$base")"
mkdir -p "$trash_dir"
chmod 700 "$trash_dir"
manifest="$trash_dir/removed.tsv"
: > "$manifest"
trap 'write_restore_sh' EXIT
moved=0
while IFS= read -r src; do
    [[ -z "$src" ]] && continue
    rel="${src#"$base_real"/}"      # path under the home base (home-agnostic)
    if [[ "$rel" == "$src" ]]; then # guard: a REMOVE path must live under the home base
        err "internal: '$src' is not under home base; skipping"
        continue
    fi
    dest="$trash_dir/$rel"
    mkdir -p "$(dirname "$dest")"
    if mv "$src" "$dest" 2> /dev/null; then
        :
    else # EXDEV / cross-device fallback: copy-verify-delete
        if rsync -a "$src" "$dest" && [[ -e "$dest" ]]; then rm -rf "$src"; else
            err "failed to move $src (backup not verified); aborting"
            exit 1
        fi
    fi
    printf '%s\t%s\n' "$src" "$dest" >> "$manifest"
    echo "Moved: $src -> ${dest#"$trash_root"/}"
    moved=$((moved + 1))
done <<< "$remove_paths"

echo
echo "Removed $moved item(s). Recoverable backup:"
echo "  $trash_dir/"
echo "Restore with:"
echo "  $trash_dir/restore.sh"

if [[ "$AS_JSON" -eq 1 ]]; then
    printf '%s\n' "$REPORT" | "$VENV_PY" -c '
import json,sys
d=json.load(sys.stdin); d["mode"]="remove"
td=sys.argv[1]; man=sys.argv[2]
removed=[]
for line in open(man, encoding="utf-8"):
    line=line.rstrip("\n")
    if not line: continue
    s,dst=line.split("\t",1); removed.append({"canonical_path":s,"backup_path":dst})
d["removed"]=removed; d["backup_dir"]=td
print(json.dumps(d))' "$trash_dir" "$manifest"
fi
