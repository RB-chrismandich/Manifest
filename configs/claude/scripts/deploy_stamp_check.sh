#!/usr/bin/env bash
# deploy_stamp_check.sh — Claude Code SessionStart hook.
#
# Nudge (once) when the local Manifest clone has advanced past the last
# ./bootstrap.sh deploy. Reads ~/.claude/config/deploy_stamp (written by
# bootstrap's write_deploy_stamp) and compares the clone's current
# deploy-source git tree hashes against it. Warns ONLY on a clean default
# branch — feature-branch / dirty-tree drift is expected WIP.
#
# Also nudges (once) when the clone's default branch is behind its upstream
# remote-tracking ref — this catches the case the tree-hash compare above
# cannot: a clone that never advanced locally (stamp matches HEAD exactly)
# but is itself many commits behind origin, so the deployed home is stale
# even though nothing here ever changed. This NEVER runs `git fetch` (a
# SessionStart hook must not make a network call that could block/slow every
# session start) — it only reads the remote-tracking ref already on disk
# from whatever fetch last happened. A clone that has never been fetched has
# no refs/remotes/origin/<branch> and stays invisible to this check.
#
# Fail-open: every error path exits 0 so a broken check never blocks a
# session. Diagnostics go to stderr only under DEPLOY_STAMP_DEBUG=1.
set -uo pipefail

# Canonical err() convention (docs/CODING_STANDARDS.md), kept for parity with
# every other script even though this hook's fail-open design (every path
# exits 0 via debug()/return, never a hard error) currently has no call site.
# shellcheck disable=SC2329
err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "deploy_stamp_check.sh: $*" >&2; else printf '%s\n' "deploy_stamp_check.sh: $*" >&2; fi; }
debug() {
    [[ "${DEPLOY_STAMP_DEBUG:-}" == "1" ]] && printf '%s\n' "deploy_stamp_check.sh: $*" >&2
    return 0
}

usage() {
    cat << 'EOF'
Usage: deploy_stamp_check.sh [-h|--help]

SessionStart hook: warns once when the Manifest git clone has changed
configs/ or skills since the last ./bootstrap.sh deploy, OR when the clone's
default branch is behind its already-fetched origin/<branch> ref (no
`git fetch` is ever run). Silent (exit 0) unless the clone is on a clean
default branch. Set DEPLOY_STAMP_DEBUG=1 for stderr diagnostics.
EOF
}

case "${1:-}" in
    -h | --help)
        usage
        exit 0
        ;;
esac

main() {
    local stamp="${HOME}/.claude/config/deploy_stamp"
    [[ -f "$stamp" ]] || {
        debug "no stamp"
        return 0
    }

    local tree_configs="" tree_skills="" dirty="" clone_path="" deployed_at="" k v
    while IFS='=' read -r k v; do
        case "$k" in
            tree_configs) tree_configs="$v" ;;
            tree_skills) tree_skills="$v" ;;
            dirty) dirty="$v" ;;
            clone_path) clone_path="$v" ;;
            deployed_at) deployed_at="$v" ;;
        esac
    done < "$stamp"

    [[ -n "$clone_path" && -d "$clone_path" ]] || {
        debug "clone path missing: $clone_path"
        return 0
    }
    git -C "$clone_path" rev-parse --git-dir > /dev/null 2>&1 || {
        debug "not a git repo"
        return 0
    }

    local def_branch cur_branch
    def_branch="$(git -C "$clone_path" symbolic-ref --quiet refs/remotes/origin/HEAD 2> /dev/null)"
    # Strip exactly the ref prefix. `##*/` would keep only the last path
    # component, truncating a slash-containing default branch (release/v2 -> v2)
    # so that refs/remotes/origin/<branch> below resolves to nothing and the
    # behind-upstream check silently no-ops.
    case "$def_branch" in
        refs/remotes/origin/*) def_branch="${def_branch#refs/remotes/origin/}" ;;
        *) def_branch="" ;;
    esac
    [[ -n "$def_branch" ]] || def_branch="main"
    cur_branch="$(git -C "$clone_path" rev-parse --abbrev-ref HEAD 2> /dev/null)"
    [[ "$cur_branch" == "$def_branch" ]] || {
        debug "on $cur_branch not $def_branch"
        return 0
    }

    [[ -z "$(git -C "$clone_path" status --porcelain -- configs .apm/skills 2> /dev/null)" ]] || {
        debug "dirty sources"
        return 0
    }

    local state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"

    # Behind-upstream check (see header comment): local-only, no `git fetch`.
    # Compares HEAD against the remote-tracking ref already on disk, so a
    # clone that has never been fetched simply never triggers this — that
    # limitation is accepted, not worked around. It is NOT reported to the user:
    # a SessionStart hook must not fetch, so it cannot distinguish "up to date"
    # from "unknown" without network, and a per-session nudge about a rare
    # condition (normal `git clone` always populates origin/*) is worse than
    # silence. It is distinguished on the debug channel below, so a diagnosis
    # run never sees an unexplained zero.
    local behind
    behind="$(git -C "$clone_path" rev-list --count "HEAD..refs/remotes/origin/$def_branch" 2> /dev/null)"
    if [[ "$behind" =~ ^[0-9]+$ && "$behind" -gt 0 ]]; then
        local upstream_sha behind_state
        upstream_sha="$(git -C "$clone_path" rev-parse "refs/remotes/origin/$def_branch" 2> /dev/null)"
        behind_state="$state_root/deploy_stamp_behind_warned"
        if [[ -z "$upstream_sha" || ! -f "$behind_state" || "$(cat "$behind_state" 2> /dev/null)" != "$upstream_sha" ]]; then
            printf '⚠ Manifest clone %s is %s commit(s) behind origin/%s — git pull, then ./bootstrap.sh to redeploy.\n' \
                "$clone_path" "$behind" "$def_branch"
            if [[ -n "$upstream_sha" ]]; then
                mkdir -p "$state_root" 2> /dev/null || true
                printf '%s\n' "$upstream_sha" > "$behind_state" 2> /dev/null || true
            fi
        else
            debug "already warned for upstream $upstream_sha"
        fi
    elif git -C "$clone_path" rev-parse --verify --quiet "refs/remotes/origin/$def_branch" > /dev/null 2>&1; then
        debug "not behind upstream"
    else
        debug "origin/$def_branch has no remote-tracking ref (never fetched) — behind-check inactive"
    fi

    local cur_configs cur_skills
    cur_configs="$(git -C "$clone_path" rev-parse HEAD:configs 2> /dev/null)" || return 0
    cur_skills="$(git -C "$clone_path" rev-parse HEAD:.apm/skills 2> /dev/null)" || return 0

    if [[ "$cur_configs" == "$tree_configs" && "$cur_skills" == "$tree_skills" && "$dirty" == "false" ]]; then
        debug "up to date"
        return 0
    fi

    local state_file="$state_root/deploy_stamp_warned"
    local combined="${cur_configs}:${cur_skills}"
    if [[ -f "$state_file" && "$(cat "$state_file" 2> /dev/null)" == "$combined" ]]; then
        debug "already warned for $combined"
        return 0
    fi

    local short_sha
    short_sha="$(git -C "$clone_path" rev-parse --short HEAD 2> /dev/null)"
    cat << EOF
⚠ Manifest deploy is stale: $clone_path ($def_branch @$short_sha) has changed
configs/ or skills since the last deploy on ${deployed_at:-unknown}.
Run ./bootstrap.sh in $clone_path to redeploy.
EOF

    mkdir -p "$state_root" 2> /dev/null || true
    printf '%s\n' "$combined" > "$state_file" 2> /dev/null || true
    return 0
}

main "$@" || true
exit 0
