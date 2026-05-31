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

# Home targets — parallel rsync so total time = slowest single target
rsync -a --delete "$SKILLS_SRC/" "$HOME/.claude/skills/" &
for dir in "$HOME/.cursor/skills" "$HOME/.gemini/skills" "$HOME/.codex/skills"; do
    [[ -d "$dir" ]] && rsync -a --delete "$SKILLS_SRC/" "$dir/" &
done
wait
