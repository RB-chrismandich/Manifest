#!/bin/bash

# Shared helpers for bootstrap.sh. This file is sourced, not executed.

# Set colors if not already defined (allows standalone usage)
# shellcheck disable=SC2034
RED="${RED:-\033[0;31m}"
# shellcheck disable=SC2034
GREEN="${GREEN:-\033[0;32m}"
# shellcheck disable=SC2034
BLUE="${BLUE:-\033[0;34m}"
# shellcheck disable=SC2034
YELLOW="${YELLOW:-\033[1;33m}"
# shellcheck disable=SC2034
CYAN="${CYAN:-\033[0;36m}"
# shellcheck disable=SC2034
BOLD="${BOLD:-\033[1m}"
# shellcheck disable=SC2034
NC="${NC:-\033[0m}" # No Color

# Check for NO_COLOR or non-interactive shell to disable colors
if [[ -n "${NO_COLOR:-}" ]] || [[ ! -t 1 ]]; then
    RED=""
    GREEN=""
    BLUE=""
    YELLOW=""
    CYAN=""
    BOLD=""
    NC=""
fi

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
    local pid
    local spin='-\|/'
    local i=0

    # If NO_COLOR is set or not a TTY, just run command without spinner
    if [[ -n "${NO_COLOR:-}" ]] || [[ ! -t 1 ]]; then
        echo -e "${CYAN}→${NC} ${msg}..."
        eval "$cmd"
        local exit_code=$?
        if [[ $exit_code -eq 0 ]]; then
            echo -e "${GREEN}✓ Done${NC}"
        else
            echo -e "${RED}✗ Failed${NC}"
        fi
        return $exit_code
    fi

    # Use a subshell for trap to avoid overwriting global traps
    (
        # Trap to restore cursor if script is interrupted
        trap 'tput cnorm 2>/dev/null' EXIT INT TERM

        # Hide cursor
        tput civis 2>/dev/null

        eval "$cmd" &
        pid=$!

        while kill -0 "$pid" 2> /dev/null; do
            i=$(((i + 1) % 4))
            printf "\r${CYAN}${spin:$i:1}${NC} %s..." "$msg"
            sleep 0.1
        done

        wait "$pid"
        exit_code=$?

        # Clear line
        printf "\r\033[K"

        if [[ $exit_code -eq 0 ]]; then
            printf "${GREEN}✓${NC} %s\n" "$msg"
        else
            printf "${RED}✗${NC} %s (failed)\n" "$msg"
        fi

        # Restore cursor
        tput cnorm 2>/dev/null
        exit $exit_code
    )
    return $?
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

    rm -rf "$link_path"
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
