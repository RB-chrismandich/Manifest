#!/usr/bin/env bash
# version_pin_hook.sh - PostToolUse adapter for version_pin.sh (warn-only)
#
# Reads the Claude Code PostToolUse JSON payload on stdin, extracts the edited
# file path, and — only for recognized version-pinned file names — runs
# version_pin.sh in warn-only mode. Advisory only: always exits 0 so it never
# blocks an edit; the pinning report (if any) is written to stderr.
#
# Wire via settings.local.json:
#   "hooks": { "PostToolUse": [ { "matcher": "Write|Edit",
#     "hooks": [ { "type": "command",
#       "command": "~/.claude/scripts/version_pin_hook.sh" } ] } ] }

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Extract tool_input.file_path from the PostToolUse payload (empty if absent).
file="$(python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
print((d.get("tool_input") or {}).get("file_path","") or "")' 2>/dev/null || true)"

[[ -n "$file" && -f "$file" ]] || exit 0

# Only act on recognized, version-pinnable file names (keeps unrelated edits quiet).
case "$(basename "$file")" in
    requirements.txt|requirements*.txt|docker-compose.yml|docker-compose.yaml|\
    compose.yml|compose.yaml|Dockerfile|Dockerfile.*|*.Dockerfile)
        "${SCRIPT_DIR}/version_pin.sh" --check "$file" >&2 || true
        ;;
esac

exit 0
