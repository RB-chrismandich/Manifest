#!/usr/bin/env bash
set -euo pipefail

err() { echo "sync-skills: $*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: sync-skills

Sync .skillshare/skills/ (source of truth) to all home targets
(~/.claude/skills + Cursor/Gemini/Codex/Antigravity symlinks) and run
skillshare sync for the Copilot target. No flags. Requires MANIFEST_ROOT
(set by bootstrap.sh).
USAGE
    exit 0
fi

[[ -z "${MANIFEST_ROOT:-}" ]] && {
    err "MANIFEST_ROOT not set. Re-run bootstrap.sh."
    exit 1
}
[[ ! -d "$MANIFEST_ROOT" ]] && {
    err "MANIFEST_ROOT '$MANIFEST_ROOT' not found."
    exit 1
}

SKILLS_SRC="$MANIFEST_ROOT/.skillshare/skills"
[[ ! -d "$SKILLS_SRC" ]] && {
    err "skills source not found: $SKILLS_SRC"
    exit 1
}

# Copilot sync via skillshare (warn and continue if not installed or fails)
if command -v skillshare > /dev/null 2>&1; then
    (cd "$MANIFEST_ROOT" && skillshare sync) || err "Warning: skillshare sync failed — continuing"
else
    err "Warning: skillshare not installed — skipping Copilot sync"
fi

# real_dir DIR — resolve a directory's physical path (portable; no readlink -f)
real_dir() { (cd "$1" 2> /dev/null && pwd -P); }

# sync_one DEST — merge-then-manifest-prune, mirroring deploy_home_skills:
# rsync WITHOUT --delete (never touches foreign skills or the manifest), then
# prune only previously-deployed skills now absent from the source, scoped by
# the .deployed-skills manifest, and atomically rewrite the manifest.
sync_one() {
    local dest="$1" manifest name src_count
    rsync -a "$SKILLS_SRC/" "$dest/" || return 1
    manifest="$dest/.deployed-skills"
    src_count=$(find "$SKILLS_SRC" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | wc -l | tr -d ' ')
    if [[ -f "$manifest" && "$src_count" -gt 0 ]]; then
        while IFS= read -r name; do
            case "$name" in
                '' | */* | .* | *..*) continue ;; # empty, path-y, hidden, traversal -> never prune
            esac
            if [[ ! -d "$SKILLS_SRC/$name" && -d "$dest/$name" ]]; then
                rm -rf "${dest:?}/${name}"
            fi
        done < "$manifest"
    fi
    # Atomic manifest write: a failed subshell must not truncate the previous one.
    if (cd "$SKILLS_SRC" && find . -mindepth 1 -maxdepth 1 -type d ! -name '.*' |
        LC_ALL=C sort | sed 's|^\./||') > "$manifest.tmp"; then
        mv "$manifest.tmp" "$manifest"
    else
        rm -f "$manifest.tmp"
    fi
}

# Home targets — parallel sync, PID-tracked so failures are visible
pids=()
targets=()

sync_one "$HOME/.claude/skills" &
pids+=($!) targets+=("$HOME/.claude/skills")
primary_real=$(real_dir "$HOME/.claude/skills" || true)
for dir in "$HOME/.cursor/skills" "$HOME/.gemini/skills" "$HOME/.codex/skills"; do
    [[ -d "$dir" ]] || continue
    if [[ -n "$primary_real" && "$(real_dir "$dir")" == "$primary_real" ]]; then
        err "skipping $dir (symlink to primary skills dir — already synced)"
        continue
    fi
    sync_one "$dir" &
    pids+=($!) targets+=("$dir")
done

failed=0
for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
        err "Warning: rsync to ${targets[$i]} failed"
        [[ "${targets[$i]}" == "$HOME/.claude/skills" ]] && failed=1
    fi
done
[[ $failed -eq 0 ]] || exit 1
