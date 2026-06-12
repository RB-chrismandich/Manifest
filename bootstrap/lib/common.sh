#!/bin/bash

# Shared helpers for bootstrap.sh. This file is sourced, not executed.

print_header() {
    echo ""
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}→${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

prompt_yes_no() {
    local question="$1"
    local default="${2:-y}"
    local prompt_suffix
    local response

    if [[ "$default" == "y" ]]; then
        prompt_suffix="[Y/n]"
    else
        prompt_suffix="[y/N]"
    fi

    echo -ne "${BOLD}${question}${NC} ${CYAN}${prompt_suffix}${NC}: "
    read -r response
    response="${response:-$default}"

    [[ "$response" =~ ^[Yy]([Ee][Ss])?$ ]]
}

command_exists() {
    command -v "$1" &> /dev/null
}

# Show a spinner while a command runs
# Usage: run_with_spinner "command args" "Loading message"
run_with_spinner() {
    local cmd="$1"
    local msg="${2:-Working}"

    (
        local log_file
        log_file=$(mktemp)
        trap 'tput cnorm 2>/dev/null || true; rm -f "$log_file"' INT TERM EXIT
        tput civis 2>/dev/null || true

        eval "$cmd" > "$log_file" 2>&1 &
        local pid=$!
        local spin='-\|/'
        local i=0

        while kill -0 "$pid" 2> /dev/null; do
            i=$(((i + 1) % 4))
            printf "\r${CYAN}${spin:$i:1}${NC} %s..." "$msg"
            sleep 0.2
        done

        local exit_code=0
        wait "$pid" || exit_code=$?

        printf "\r\033[K"
        if [ "$exit_code" -ne 0 ]; then
            cat "$log_file"
        fi
        exit "$exit_code"
    )
}

# Create/recreate a symlink at link_path pointing to target
create_symlink() {
    local link_path="$1"
    local target="$2"
    local label="$3"

    if [[ ! -e "$target" ]]; then
        print_warning "Symlink target not found: $target (skipping $label)"
        return 0
    fi

    # A real (non-symlink) path here is user content — back it up instead of
    # silently destroying it with rm -rf (issue #321)
    if [[ -e "$link_path" && ! -L "$link_path" ]]; then
        local backup
        backup="${link_path}.backup.$(date +%Y%m%d_%H%M%S)"
        print_warning "$link_path exists as a real path — backing up to $backup"
        mv "$link_path" "$backup"
    else
        rm -rf "$link_path"
    fi
    ln -sf "$target" "$link_path"
    print_success "Symlinked $link_path -> $target"
}

# Link shared directories from ~/.claude into another config directory.
# Third arg `include_skills=true` also links the shared skills directory.
link_shared_assets() {
    local destination_dir="$1"
    local shared_name="${2:-Config}"
    local include_skills="${3:-false}"

    local symlinks=(
        "scripts:$TARGET_DIR/scripts"
        "config:$TARGET_DIR/config"
        "prompts:$TARGET_DIR/prompts"
        ".plans:$TARGET_DIR/.plans"
    )
    if [[ "$include_skills" == "true" ]]; then
        symlinks+=("skills:$TARGET_DIR/skills")
    fi

    local entry
    for entry in "${symlinks[@]}"; do
        local name="${entry%%:*}"
        local target="${entry#*:}"
        local link_path="$destination_dir/$name"
        create_symlink "$link_path" "$target" "${shared_name} $name"
    done
}

# Deploy skills into a tool's real skills dir from the PHYSICAL skillshare source.
# Always sources the real .skillshare/skills dir (never the compat symlink).
# Manifest-scoped prune (FR-005a, specs/003): skills we previously deployed and
# that have since been removed from the source of truth are pruned from dest,
# but ~/.claude/skills can legitimately hold skills installed by other
# tools/plugins — those are never in the manifest and are never touched.
deploy_home_skills() {
    local src="$1"
    local dest="$2"

    if [[ ! -d "$src" ]]; then
        print_error "Skill source not found: $src"
        return 1
    fi

    # If dest is a stray symlink (e.g. from an older install that copied the
    # compat symlink), drop it so we deploy into a real directory, not its target.
    [[ -L "$dest" ]] && rm -f "$dest"
    mkdir -p "$dest"
    rsync -a "$src"/ "$dest"/

    # Prune previously-deployed skills now absent from the source.
    # Safety bounds: (a) an empty source (failed checkout / wrong path that
    # still exists) must never mass-prune dest — require >=1 source skill;
    # (b) manifest entries are validated as plain single-level names so a
    # corrupted manifest can never drive rm -rf outside dest.
    local manifest="$dest/.deployed-skills"
    local src_count
    src_count=$(find "$src" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | wc -l | tr -d ' ')
    if [[ -f "$manifest" && "$src_count" -gt 0 ]]; then
        local name
        while IFS= read -r name; do
            case "$name" in
                ''|*/*|.*|*..*) continue ;;   # empty, path-y, hidden, traversal -> never prune
            esac
            if [[ ! -d "$src/$name" && -d "$dest/$name" ]]; then
                rm -rf "${dest:?}/${name}"
                print_info "Pruned removed skill: $name"
            fi
        done < "$manifest"
    fi
    # Atomic manifest write: a failed subshell must not truncate the previous
    # manifest (that would silently disable future pruning).
    if (cd "$src" && find . -mindepth 1 -maxdepth 1 -type d ! -name '.*' \
        | LC_ALL=C sort | sed 's|^\./||') > "$manifest.tmp"; then
        mv "$manifest.tmp" "$manifest"
    else
        rm -f "$manifest.tmp"
    fi

    print_success "Deployed skills: $src -> $dest"
}
