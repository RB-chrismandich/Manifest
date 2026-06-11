#!/usr/bin/env bash
set -euo pipefail

err() { echo "sync-skills: $*" >&2; }

[[ -z "${MANIFEST_ROOT:-}" ]] && { err "MANIFEST_ROOT not set. Re-run bootstrap.sh."; exit 1; }
[[ ! -d "$MANIFEST_ROOT" ]]  && { err "MANIFEST_ROOT '$MANIFEST_ROOT' not found."; exit 1; }

SKILLS_SRC="$MANIFEST_ROOT/.skillshare/skills"
[[ ! -d "$SKILLS_SRC" ]] && { err "skills source not found: $SKILLS_SRC"; exit 1; }

# Copilot sync via skillshare (warn and continue if not installed or fails)
if command -v skillshare > /dev/null 2>&1; then
    (cd "$MANIFEST_ROOT" && skillshare sync) || err "Warning: skillshare sync failed — continuing"
else
    err "Warning: skillshare not installed — skipping Copilot sync"
fi

# Home targets — parallel rsync, PID-tracked so failures are visible
pids=()
targets=()

rsync -a --delete "$SKILLS_SRC/" "$HOME/.claude/skills/" & pids+=($!) targets+=("$HOME/.claude/skills")
for dir in "$HOME/.cursor/skills" "$HOME/.gemini/skills" "$HOME/.codex/skills"; do
    [[ -d "$dir" ]] && { rsync -a --delete "$SKILLS_SRC/" "$dir/" & pids+=($!) targets+=("$dir"); }
done

failed=0
for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
        err "Warning: rsync to ${targets[$i]} failed"
        [[ "${targets[$i]}" == "$HOME/.claude/skills" ]] && failed=1
    fi
done
[[ $failed -eq 0 ]] || exit 1
