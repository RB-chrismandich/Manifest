#!/usr/bin/env bash
# deploy_stamp_check.sh — Claude Code SessionStart hook.
#
# Nudge (once) when the local Manifest clone has advanced past the last
# ./bootstrap.sh deploy. Reads ~/.claude/config/deploy_stamp (written by
# bootstrap's write_deploy_stamp) and compares the clone's current
# deploy-source git tree hashes against it. Warns ONLY on a clean default
# branch — feature-branch / dirty-tree drift is expected WIP.
#
# Fail-open: every error path exits 0 so a broken check never blocks a
# session. Diagnostics go to stderr only under DEPLOY_STAMP_DEBUG=1.
set -uo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "deploy_stamp_check.sh: $*" >&2; else printf '%s\n' "deploy_stamp_check.sh: $*" >&2; fi; }
debug() {
    [[ "${DEPLOY_STAMP_DEBUG:-}" == "1" ]] && err "$*"
    return 0
}

usage() {
    cat << 'EOF'
Usage: deploy_stamp_check.sh [-h|--help]

SessionStart hook: warns once when the Manifest git clone has changed
configs/ or skills since the last ./bootstrap.sh deploy. Silent (exit 0)
unless the clone is on a clean default branch AND its sources differ from
the recorded stamp. Set DEPLOY_STAMP_DEBUG=1 for stderr diagnostics.
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
    def_branch="${def_branch##*/}"
    [[ -n "$def_branch" ]] || def_branch="main"
    cur_branch="$(git -C "$clone_path" rev-parse --abbrev-ref HEAD 2> /dev/null)"
    [[ "$cur_branch" == "$def_branch" ]] || {
        debug "on $cur_branch not $def_branch"
        return 0
    }

    [[ -z "$(git -C "$clone_path" status --porcelain -- configs .skillshare/skills 2> /dev/null)" ]] || {
        debug "dirty sources"
        return 0
    }

    local cur_configs cur_skills
    cur_configs="$(git -C "$clone_path" rev-parse HEAD:configs 2> /dev/null)" || return 0
    cur_skills="$(git -C "$clone_path" rev-parse HEAD:.skillshare/skills 2> /dev/null)" || return 0

    if [[ "$cur_configs" == "$tree_configs" && "$cur_skills" == "$tree_skills" && "$dirty" == "false" ]]; then
        debug "up to date"
        return 0
    fi

    local state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
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
