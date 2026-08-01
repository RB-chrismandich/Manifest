#!/usr/bin/env bash
set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "sync-skills: $*" >&2; else printf '%s\n' "sync-skills: $*" >&2; fi; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: sync-skills

Sync .apm/skills/ (source of truth) to all home targets
(~/.claude/skills + Cursor/Gemini/Codex/Antigravity symlinks). No flags.
Requires MANIFEST_ROOT (set by bootstrap.sh).
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

SKILLS_SRC="$MANIFEST_ROOT/.apm/skills"
[[ ! -d "$SKILLS_SRC" ]] && {
    err "skills source not found: $SKILLS_SRC"
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# T015/FR-027: stand down for a domain APM owns. Deployed to ~/.local/bin, so
# the library is resolved from the repo first and the deployed sibling second.
# shellcheck disable=SC1090,SC1091
for _lib in "$MANIFEST_ROOT/configs/claude/scripts/apm_domains_lib.sh" \
    "$SCRIPT_DIR/apm_domains_lib.sh" "$HOME/.claude/scripts/apm_domains_lib.sh"; do
    [[ -f "$_lib" ]] && {
        source "$_lib"
        break
    }
done
unset _lib

# T2.2 (spec 674): a retired domain has no writer at all. Checked first, because
# this script declines ONLY while apm owns the domain — under the two-state
# registry, moving `skills` out of `domains:` would have re-armed it.
if declare -f domain_retired > /dev/null 2>&1 && domain_retired skills; then
    echo "sync-skills: skipping 'skills' — retired from both pipelines."
    echo "sync-skills: plugins own it now; use 'claude plugin update <bundle>'."
    exit 0
fi

if declare -f apm_owns_domain > /dev/null 2>&1 && apm_owns_domain skills; then
    # SAY it. A silent no-op reads as success, and a contributor whose skill
    # edit never reached their home will debug the edit, not the tool. Naming
    # the replacement matters just as much: "declined to act" with no
    # alternative is a dead end (FR-021 requires the workflow keep working).
    echo "sync-skills: skipping 'skills' — APM owns this domain now."
    echo "sync-skills: use ${APM_DOMAIN_REPLACEMENT_CMD:-apm-dev-sync} instead (publish-free; also removes deleted skills)."
    exit 0
fi

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

# load_agent_roster_home_dirs -> "name<TAB>home_dir<TAB>skills_sync" lines, one per agent, in
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

    out="$(
        python3 - "$roster_path" 2> /dev/null << 'PY'
import sys

import yaml

try:
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f) or {}
    agents = data.get("agents") or {}
    for name, entry in agents.items():
        if not isinstance(entry, dict):
            continue
        # skills_sync defaults to "true" when absent so a roster written
        # before the field existed keeps syncing every secondary home.
        sync = entry.get("skills_sync", True)
        print(f"{name}\t{entry.get('home_dir', '')}\t{'true' if sync else 'false'}")
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
            if (name != "") { print name "\t" home "\t" sync }
            line = $0
            sub(/^  /, "", line)
            sub(/:[[:space:]]*$/, "", line)
            name = line
            home = ""
            sync = "true"
            next
        }
        in_agents && /^    home_dir:/ {
            val = $0
            sub(/^    home_dir:[[:space:]]*/, "", val)
            gsub(/^"|"$/, "", val)
            home = val
            next
        }
        in_agents && /^    skills_sync:/ {
            val = $0
            sub(/^    skills_sync:[[:space:]]*/, "", val)
            gsub(/^"|"$/, "", val)
            sync = val
            next
        }
        END { if (name != "") print name "\t" home "\t" sync }
    ' "$1"
}

# Roster storage uses parallel indexed arrays, not associative arrays --
# mirrors check_status.sh (targets bash 3.2 / stock macOS /bin/bash, which
# has no `declare -A`).
declare -a ROSTER_NAMES=()
declare -a ROSTER_HOME_DIRS=()
declare -a ROSTER_SKILLS_SYNC=()
while IFS=$'\t' read -r r_name r_home r_sync; do
    [[ -z "$r_name" ]] && continue
    ROSTER_NAMES+=("$r_name")
    ROSTER_HOME_DIRS+=("$r_home")
    # Absent/blank field -> "true": only an explicit `skills_sync: false`
    # opts an agent out, so an older roster keeps its historical behavior.
    [[ "$r_sync" == "false" ]] && ROSTER_SKILLS_SYNC+=("false") || ROSTER_SKILLS_SYNC+=("true")
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
    # Literal ~/.<name> form, matching how tiers 1/2 store agent_roster.yml's
    # own home_dir values -- deliberately NOT pre-expanded here, so the single
    # expansion step below (line ~150) applies uniformly regardless of which
    # tier populated this array.
    # shellcheck disable=SC2088 # intentional: literal ~ kept unexpanded, see above
    ROSTER_HOME_DIRS=("~/.claude" "~/.gemini" "~/.cursor" "~/.codex" "~/.antigravity")
    # devin is deliberately absent: it has no skills directory of its own to
    # sync (see the skills_sync note below), so the pre-devin 4 secondary
    # targets remain exactly the right fallback set.
    ROSTER_SKILLS_SYNC=("true" "true" "true" "true" "true")
fi

# Secondary sync targets = every roster agent's home_dir/skills EXCEPT
# claude (the primary target, dispatched above unconditionally) and any agent
# whose roster entry sets `skills_sync: false`.
#
# devin is the only skills_sync: false agent: the Devin CLI already discovers
# ~/.claude/skills natively, so writing a second copy under its home would
# register every skill TWICE (`/devin:env-check` alongside `/claude:env-check`
# — measured against devin 3000.2.17), which halves the signal density of the
# skill listing instead of adding a single new skill.
secondary_dirs=()
for i in "${!ROSTER_NAMES[@]}"; do
    [[ "${ROSTER_NAMES[$i]}" == "claude" ]] && continue
    [[ "${ROSTER_SKILLS_SYNC[$i]}" == "false" ]] && continue
    home="${ROSTER_HOME_DIRS[$i]}"
    [[ -z "$home" ]] && continue
    home="${home/#\~/$HOME}"
    secondary_dirs+=("$home/skills")
done

# The Copilot (.github/skills) sync that skillshare owned was retired
# 2026-07-27 with skillshare itself (FR-021a). Home targets below are unaffected.

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
