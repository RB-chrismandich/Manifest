#!/bin/bash

# Shared helpers for bootstrap.sh. This file is sourced, not executed.

# Ensure cursor is restored on exit or interruption
trap 'tput cnorm 2>/dev/null' EXIT INT TERM

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
    local log_file

    # Create secure temporary file for output capture
    log_file=$(mktemp) || return 1

    # Hide cursor if possible
    tput civis 2>/dev/null

    # Run command in background, redirecting both stdout and stderr to log file
    eval "$cmd" > "$log_file" 2>&1 &
    pid=$!

    # Spin loop while process is running
    while kill -0 "$pid" 2> /dev/null; do
        i=$(((i + 1) % 4))
        # Use %b to interpret color codes correctly
        printf "\r%b%s%b %s..." "$CYAN" "${spin:$i:1}" "$NC" "$msg"
        sleep 0.1
    done

    # Wait for completion and capture exit code
    wait "$pid"
    local exit_code=$?

    # Clear the line
    printf "\r\033[K"

    # Restore cursor
    tput cnorm 2>/dev/null

    # If command failed, show error and output
    if [ $exit_code -ne 0 ]; then
        print_error "Command failed: $cmd"
        if [ -s "$log_file" ]; then
            echo -e "${RED}Output:${NC}"
            cat "$log_file"
        fi
    fi

    # Cleanup
    rm -f "$log_file"
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
