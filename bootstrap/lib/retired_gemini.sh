#!/bin/bash
# help-coverage: exempt — sourced bootstrap helper library, not a user-facing entry point
# Retirement cleanup for the removed Gemini CLI harness. Sourced by deploy.sh.
#
# Earlier bootstraps deployed Gemini CLI assets into ~/.gemini. That directory
# is still live: Antigravity's agy CLI (Gemini-CLI lineage) reads ~/.gemini/config
# and ~/.gemini/GEMINI.md, and stores its own antigravity* state there. So this
# removes only what is provably Manifest's Gemini CLI deployment:
#   - the prompts/scripts/skills/.plans symlinks, and only when they point into
#     ~/.claude or ~/.manifest;
#   - ~/.gemini/commands/*.toml files whose name and SHA-256 match a command file
#     Manifest shipped (bootstrap/data/retired_gemini_commands.sha256).
# It never touches config, GEMINI.md, settings.json, antigravity* entries, or
# credentials, and never removes a real directory or a foreign symlink.

RETIRED_GEMINI_LINKS=(prompts scripts skills .plans)

_retired_gemini_sha256() {
    if command -v sha256sum > /dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# True when a symlink's target is inside a Manifest-owned tree.
_retired_gemini_link_is_manifest() {
    local target
    target="$(readlink "$1")" || return 1
    case "$target" in
        "${TARGET_DIR:-$HOME/.claude}" | "${TARGET_DIR:-$HOME/.claude}"/* | \
            "${MANIFEST_STATE_DIR:-$HOME/.manifest}" | "${MANIFEST_STATE_DIR:-$HOME/.manifest}"/*)
            return 0
            ;;
    esac
    return 1
}

_retire_gemini_commands() {
    local commands_dir="$1" manifest_file="$2"
    [[ -d "$commands_dir" && ! -L "$commands_dir" ]] || return 0
    if [[ ! -f "$manifest_file" ]]; then
        print_warning "Retired Gemini command list missing: $manifest_file (commands left in place)"
        return 0
    fi
    local file name digest removed=0
    for file in "$commands_dir"/*.toml; do
        [[ -f "$file" && ! -L "$file" ]] || continue
        name="$(basename "$file")"
        digest="$(_retired_gemini_sha256 "$file")"
        if grep -qxF "$digest  $name" "$manifest_file"; then
            rm -f "$file"
            removed=$((removed + 1))
        fi
    done
    if [[ $removed -gt 0 ]]; then
        print_success "Removed $removed retired Gemini CLI command file(s) from $commands_dir"
    fi
    # Only an emptied directory goes; any user command keeps it.
    rmdir "$commands_dir" 2> /dev/null || true
}

# retire_gemini_cli_deployment [gemini-home]
retire_gemini_cli_deployment() {
    local home_dir="${1:-${AGY_GEMINI_HOME:-$HOME/.gemini}}"
    [[ -d "$home_dir" ]] || return 0
    local name link
    for name in "${RETIRED_GEMINI_LINKS[@]}"; do
        link="$home_dir/$name"
        if [[ -L "$link" ]] && _retired_gemini_link_is_manifest "$link"; then
            rm -f "$link"
            print_success "Removed retired Gemini CLI link $link"
        fi
    done
    _retire_gemini_commands "$home_dir/commands" \
        "${SCRIPT_DIR:-.}/bootstrap/data/retired_gemini_commands.sha256"
    return 0
}
