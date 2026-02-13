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

# Optimized sleep using read -t and coproc (Bash 4+) to avoid fork overhead
_init_fast_sleep() {
    # Check for Bash 4+ and coproc support
    if [[ "${BASH_VERSINFO[0]}" -ge 4 ]]; then
        # Use eval to prevent syntax errors on older Bash versions
        # Use read -t instead of sleep so it auto-terminates when the pipe closes (parent exit)
        eval "coproc _SLEEP_PROC { read -t 31536000; }" 2>/dev/null
        # Get the file descriptor from the coproc array
        eval "_FAST_SLEEP_FD=\${_SLEEP_PROC[0]}"
    fi
}

fast_sleep() {
    local duration="$1"

    # Lazy init
    if [[ -z "$_FAST_SLEEP_FD" ]]; then
        _init_fast_sleep
        # Mark as initialized to -1 if failed or not supported, to avoid retry
        if [[ -z "$_FAST_SLEEP_FD" ]]; then
            _FAST_SLEEP_FD="-1"
        fi
    fi

    if [[ "$_FAST_SLEEP_FD" != "-1" ]]; then
        # Use read -t on the pipe. Pipe has no data, so it times out.
        # This avoids spawning a 'sleep' process.
        # shellcheck disable=SC2162
        read -t "$duration" -u "$_FAST_SLEEP_FD" 2>/dev/null || true
    else
        # Fallback for Bash 3.2 (macOS) or if coproc failed
        sleep "$duration"
    fi
}

# Show a spinner while a command runs
# Usage: run_with_spinner "command args" "Loading message"
run_with_spinner() {
    local cmd="$1"
    local msg="${2:-Working}"
    local pid
    local spin='-\|/'
    local i=0

    eval "$cmd" &
    pid=$!

    while kill -0 "$pid" 2> /dev/null; do
        i=$(((i + 1) % 4))
        printf "\r${CYAN}${spin:$i:1}${NC} %s..." "$msg"
        fast_sleep 0.2
    done

    wait "$pid"
    local exit_code=$?
    printf "\r\033[K"
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
