#!/usr/bin/env bash
set -euo pipefail

[[ -z "${MANIFEST_ROOT:-}" ]] && { echo "Error: MANIFEST_ROOT not set. Re-run bootstrap.sh." >&2; exit 1; }
[[ ! -d "$MANIFEST_ROOT" ]]  && { echo "Error: MANIFEST_ROOT '$MANIFEST_ROOT' not found." >&2; exit 1; }

SKILLS_SRC="$MANIFEST_ROOT/.skillshare/skills"
[[ ! -d "$SKILLS_SRC" ]] && { echo "Error: skills source not found: $SKILLS_SRC" >&2; exit 1; }

# Copilot sync via skillshare (warn and continue if not installed or fails)
if command -v skillshare > /dev/null 2>&1; then
    (cd "$MANIFEST_ROOT" && skillshare sync) || echo "Warning: skillshare sync failed — continuing"
else
    echo "Warning: skillshare not installed — skipping Copilot sync"
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
        echo "Warning: rsync to ${targets[$i]} failed" >&2
        [[ "${targets[$i]}" == "$HOME/.claude/skills" ]] && failed=1
    fi
done
[[ $failed -eq 0 ]] || exit 1
