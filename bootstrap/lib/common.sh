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

    # If not interactive or NO_COLOR set, just run the command
    if [[ ! -t 1 ]] || [[ -n "${NO_COLOR:-}" ]] || [[ "${TERM:-}" == "dumb" ]]; then
        print_step "$msg..."
        eval "$cmd"
        return $?
    fi

    local pid
    local spin='-\|/'
    local i=0
    local temp_log
    temp_log=$(mktemp)

    # Run command in background, redirecting output to temp file
    # We use a subshell and trap to ensure cleanup if killed
    (eval "$cmd") > "$temp_log" 2>&1 &
    pid=$!

    # Hide cursor
    tput civis 2>/dev/null || printf "\033[?25l"

    # Spin while process is running
    while kill -0 "$pid" 2> /dev/null; do
        i=$(((i + 1) % 4))
        printf "\r${CYAN}%s${NC} %s..." "${spin:$i:1}" "$msg"
        sleep 0.1
    done

    wait "$pid"
    local exit_code=$?

    # Restore cursor and clear line
    tput cnorm 2>/dev/null || printf "\033[?25h"
    printf "\r\033[K"

    if [ $exit_code -eq 0 ]; then
        print_success "$msg"
    else
        print_error "$msg failed"
        echo -e "${RED}Error log:${NC}"
        cat "$temp_log"
    fi

    rm -f "$temp_log"
    return $exit_code
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
