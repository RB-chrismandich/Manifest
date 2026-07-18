#!/usr/bin/env bash
set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "sync-skills: $*" >&2; else printf '%s\n' "sync-skills: $*" >&2; fi; }

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# resolve_agent_roster_path -> the agent_roster.yml to read. Same precedence
# as check_status.sh's resolve_agent_roster_path: MANIFEST_AGENT_ROSTER (test
# fixtures) > the deployed home copy > the repo-relative sibling of this
# script.
resolve_agent_roster_path() {
    if [[ -n "${MANIFEST_AGENT_ROSTER:-}" ]]; then
        echo "$MANIFEST_AGENT_ROSTER"
    elif [[ -f "$HOME/.claude/config/agent_roster.yml" ]]; then
        echo "$HOME/.claude/config/agent_roster.yml"
    else
        echo "$SCRIPT_DIR/../config/agent_roster.yml"
    fi
}

# load_agent_roster_home_dirs -> "name<TAB>home_dir" lines, one per agent, in
# the registry's declaration order. Missing/malformed registry yields no
# lines. Mirrors check_status.sh's load_agent_roster_tsv two-tier parse:
# python3 + PyYAML primary (this codebase's established idiom for a bash
# script reading YAML), falling back to an awk hand-parser (no PyYAML
# required) if that yields nothing -- no python3, or a python3 without the
# yaml module (observed: stock macOS /usr/bin/python3 has no PyYAML). Unlike
# check_status.sh, this script runs under `set -euo pipefail`, so the python3
# command substitution below is followed by `|| true` -- without it, a
# non-zero python3 exit (e.g. the ImportError from a missing PyYAML) would
# trip errexit inside this function's process-substitution subshell and
# abort before ever reaching the fallback, defeating the tier it exists for.
load_agent_roster_home_dirs() {
    local roster_path out
    roster_path="$(resolve_agent_roster_path)"
    [[ -f "$roster_path" ]] || return 0

    out="$(python3 - "$roster_path" 2> /dev/null << 'PY'
import sys

import yaml

try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f) or {}
    agents = data.get("agents") or {}
    for name, entry in agents.items():
        if not isinstance(entry, dict):
            continue
        print(f"{name}\t{entry.get('home_dir', '')}")
except Exception:
    pass
PY
    )" || true
    if [[ -n "$out" ]]; then
        printf '%s\n' "$out"
        return 0
    fi

    load_agent_roster_home_dirs_fallback "$roster_path"
}

# load_agent_roster_home_dirs_fallback ROSTER_PATH -> same TSV shape as
# above, hand-parsed with awk against agent_roster.yml's fixed indentation
# (2-space agent-name headers, 4-space fields) -- no PyYAML required.
# Mirrors check_status.sh's load_agent_roster_tsv_fallback.
load_agent_roster_home_dirs_fallback() {
    awk '
        /^agents:[[:space:]]*$/ { in_agents = 1; next }
        in_agents && /^[^[:space:]]/ { in_agents = 0 }
        in_agents && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
            if (name != "") { print name "\t" home }
            line = $0
            sub(/^  /, "", line)
            sub(/:[[:space:]]*$/, "", line)
            name = line
            home = ""
            next
        }
        in_agents && /^    home_dir:/ {
            val = $0
            sub(/^    home_dir:[[:space:]]*/, "", val)
            gsub(/^"|"$/, "", val)
            home = val
            next
        }
        END { if (name != "") print name "\t" home }
    ' "$1"
}

# Roster storage uses parallel indexed arrays, not associative arrays --
# mirrors check_status.sh (targets bash 3.2 / stock macOS /bin/bash, which
# has no `declare -A`).
declare -a ROSTER_NAMES=()
declare -a ROSTER_HOME_DIRS=()
while IFS=$'\t' read -r r_name r_home; do
    [[ -z "$r_name" ]] && continue
    ROSTER_NAMES+=("$r_name")
    ROSTER_HOME_DIRS+=("$r_home")
done < <(load_agent_roster_home_dirs)

# Third tier: both the python3+PyYAML parse AND the awk fallback above
# produced nothing -- missing/corrupted agent_roster.yml, or a bad
# MANIFEST_AGENT_ROSTER override pointing nowhere. Mirrors check_status.sh's
# same third-tier fallback (and its documented rationale) for this file:
# without it a totally-unreadable roster silently collapses to "sync
# nothing" instead of preserving this script's pre-roster behavior of
# always syncing the 4 historical secondary targets.
if [[ ${#ROSTER_NAMES[@]} -eq 0 ]]; then
    ROSTER_NAMES=(claude gemini cursor codex antigravity)
    ROSTER_HOME_DIRS=("$HOME/.claude" "$HOME/.gemini" "$HOME/.cursor" "$HOME/.codex" "$HOME/.antigravity")
fi

# Secondary sync targets = every roster agent's home_dir/skills EXCEPT
# claude, which is the primary target (dispatched above, unconditionally).
secondary_dirs=()
for i in "${!ROSTER_NAMES[@]}"; do
    [[ "${ROSTER_NAMES[$i]}" == "claude" ]] && continue
    home="${ROSTER_HOME_DIRS[$i]}"
    [[ -z "$home" ]] && continue
    home="${home/#\~/$HOME}" # agent_roster.yml home_dir values are always ~/.<name>
    secondary_dirs+=("$home/skills")
done

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
for dir in ${secondary_dirs[@]+"${secondary_dirs[@]}"}; do
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
