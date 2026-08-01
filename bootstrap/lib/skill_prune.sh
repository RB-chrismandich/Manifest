#!/usr/bin/env bash
# skill_prune.sh — decide which deployed skill directories to remove.
#
# Split out of common.sh, which reached its 600-line constitution ceiling. One
# responsibility: given a source tree and a deployed tree, name the directories
# that should go.
#
# Sourced by common.sh; not executable on its own.
# help-coverage: exempt — library, no user-facing entry point.

# prune_removed_skills <src> <dest> <src_count>
#
# Prunes from the UNION of the deploy manifest and the catalog registry, because
# neither alone is sufficient:
#
#   manifest  — records what WAS deployed, so it is the only thing that can catch
#               a RETIRED skill (gone from both source and registry). But since
#               SC-006 stood both of its writers down while apm kept mutating the
#               tree it is frozen: measured 2026-07-30 as 108 entries against 109
#               dirs, with code-audit-constitution on disk and unlisted. Anything
#               it missed was invisible to the prune.
#   registry  — records what SHOULD exist now, catching exactly what a frozen
#               manifest missed. Restricted to names Manifest owns, so a user's
#               `claude plugin init` scaffold is never a prune candidate.
#
# Prunable if (listed OR ours) AND absent from source. An empty source never
# mass-prunes (caller enforces src_count > 0), and entries are validated as plain
# single-level names so a corrupted list cannot drive rm -rf outside dest.
prune_removed_skills() {
    local src="$1" dest="$2" src_count="$3"
    local manifest="$dest/.deployed-skills"
    local prune_candidates="$dest/.prune-candidates.$$"
    : > "$prune_candidates"
    [[ -f "$manifest" ]] && cat "$manifest" >> "$prune_candidates"
    local registry="${MANIFEST_SKILL_REGISTRY:-$(dirname "$dest")/config/skill_policies.yml}"
    if [[ -r "$registry" ]]; then
        sed -n 's/^    - \([a-z0-9][a-z0-9-]*\)$/\1/p' "$registry" >> "$prune_candidates"
    fi

    if [[ -s "$prune_candidates" && "$src_count" -gt 0 ]]; then
        local name
        while IFS= read -r name; do
            case "$name" in
                '' | */* | .* | *..*) continue ;; # empty, path-y, hidden, traversal -> never prune
            esac
            if [[ ! -d "$src/$name" && -d "$dest/$name" ]]; then
                rm -rf "${dest:?}/${name}"
                print_info "Pruned removed skill: $name"
            fi
        done < <(sort -u "$prune_candidates")
    fi
    rm -f "$prune_candidates"
}
