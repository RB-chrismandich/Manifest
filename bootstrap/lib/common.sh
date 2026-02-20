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

# Show a spinner while a command runs, capturing output to a log file.
# On success: output is discarded.
# On failure: output is printed to stderr.
# Usage: run_with_spinner "Loading message" command [args...]
run_with_spinner() {
    local msg="$1"
    shift
    local pid
    local spin='-\|/'
    local i=0
    local temp_log
    temp_log=$(mktemp)

    # Hide cursor if possible
    tput civis 2>/dev/null || true

    # Ensure cursor restoration and cleanup on interrupt
    trap 'tput cnorm 2>/dev/null; rm -f "$temp_log"; exit 1' INT TERM

    # Run command in background, redirecting both stdout and stderr to temp log
    "$@" > "$temp_log" 2>&1 &
    pid=$!

    # Spin while process is running
    while kill -0 "$pid" 2> /dev/null; do
        i=$(((i + 1) % 4))
        # Print spinner and message, ensuring no newline
        printf "\r${CYAN}${spin:$i:1}${NC} %s..." "$msg"
        sleep 0.1
    done

    # Wait for process to finish and capture exit code
    wait "$pid"
    local exit_code=$?

    # Restore cursor if possible
    tput cnorm 2>/dev/null || true

    # Clear trap
    trap - INT TERM

    # Clear the spinner line
    printf "\r\033[K"

    if [ $exit_code -eq 0 ]; then
        rm -f "$temp_log"
        return 0
    else
        # Print failure message and dump log
        echo -e "${RED}✗ Failed: $msg${NC}"
        echo -e "${YELLOW}--- Error Output ---${NC}"
        cat "$temp_log"
        echo -e "${YELLOW}--------------------${NC}"
        rm -f "$temp_log"
        return $exit_code
    fi
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
