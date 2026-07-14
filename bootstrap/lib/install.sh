#!/bin/bash

# Install and platform helpers for bootstrap.sh. This file is sourced, not executed.

check_platform() {
    case "$PLATFORM" in
        macos)
            print_success "Running on macOS $(sw_vers -productVersion)"
            ;;
        linux)
            local version=""
            if [[ -f /etc/os-release ]]; then
                # /etc/os-release is a runtime-only distro file with no static
                # equivalent shellcheck can follow; content is host-specific.
                # shellcheck disable=SC1091
                . /etc/os-release
                version="$PRETTY_NAME"
            else
                version="$(uname -r)"
            fi
            print_success "Running on Linux: $version"
            if [[ -n "$PKG_MANAGER" ]]; then
                print_info "Package manager: $PKG_MANAGER"
            else
                print_warning "No supported package manager detected"
            fi
            ;;
        *)
            print_error "Unsupported platform: $(uname -s)"
            print_info "This script supports macOS and Linux"
            exit 1
            ;;
    esac
}

# Check and install Homebrew (macOS) or ensure package manager is available (Linux)
install_package_manager() {
    if [[ "$PLATFORM" == "macos" ]]; then
        print_step "Checking for Homebrew..."

        if command_exists brew; then
            print_success "Homebrew is installed"
            print_step "Updating Homebrew..."
            brew update --quiet
        else
            print_warning "Homebrew not found"
            if prompt_yes_no "Install Homebrew?"; then
                print_step "Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

                # Add Homebrew to PATH for Apple Silicon
                if [[ -f "/opt/homebrew/bin/brew" ]]; then
                    # shellcheck disable=SC1090
                    source <(/opt/homebrew/bin/brew shellenv)
                fi
                # Add Homebrew to PATH for Intel Mac
                if [[ -f "/usr/local/bin/brew" ]]; then
                    # shellcheck disable=SC1090
                    source <(/usr/local/bin/brew shellenv)
                fi
                print_success "Homebrew installed"
            else
                print_warning "Homebrew not installed - some installations may fail"
            fi
        fi
    elif [[ "$PLATFORM" == "linux" ]]; then
        print_step "Checking package manager..."

        if [[ -z "$PKG_MANAGER" ]]; then
            print_warning "No supported package manager found"
            print_info "Supported: apt, dnf, yum, pacman, zypper"
            print_info "You may need to install dependencies manually"
        else
            print_success "Package manager available: $PKG_MANAGER"

            # Update package lists
            case "$PKG_MANAGER" in
                apt)
                    if prompt_yes_no "Update apt package lists?"; then
                        print_step "Updating package lists..."
                        sudo apt-get update -qq
                    fi
                    ;;
                dnf | yum)
                    # dnf/yum auto-updates metadata
                    ;;
                pacman)
                    if prompt_yes_no "Sync pacman database?"; then
                        print_step "Syncing database..."
                        sudo pacman -Sy --noconfirm
                    fi
                    ;;
            esac
        fi
    fi
}

# Check Python installation (required for parallel_agent.py)
# Detects and prefers stable Python versions (>= 3.9, not alpha/beta/rc)
check_python() {
    print_step "Checking for Python..."

    # Find all Python installations (prefer specific stable versions)
    local python_candidates=(
        "/usr/local/bin/python3.14" # Homebrew Python 3.14 (latest stable)
        "/usr/local/bin/python3.13" # Homebrew Python 3.13
        "/usr/local/bin/python3.12" # Homebrew Python 3.12
        "/usr/bin/python3"          # macOS system Python (usually stable)
        "/usr/local/bin/python3"    # Homebrew Python (generic)
        "python3"                   # PATH python3
        "python"                    # PATH python
    )

    local best_python=""
    local best_version=""
    local best_score=0

    for py_cmd in "${python_candidates[@]}"; do
        # Check if command exists
        if ! command -v "$py_cmd" &> /dev/null; then
            continue
        fi

        # Get full version
        local version
        version=$($py_cmd --version 2>&1 | awk '{print $2}')
        if [[ -z "$version" ]]; then
            continue
        fi

        # Parse major.minor
        local major minor
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)

        # Skip Python 2.x
        if [[ "$major" -lt 3 ]]; then
            continue
        fi

        # Calculate score (prefer stable >= 3.9)
        local score=0

        # Prefer 3.9+ (modern Python with good library support)
        if [[ "$major" -eq 3 ]] && [[ "$minor" -ge 9 ]] && [[ "$minor" -le 20 ]]; then
            score=$((score + 100))
            # Bonus for newer stable versions (3.12+)
            if [[ "$minor" -ge 12 ]]; then
                score=$((score + 10))
            fi
        elif [[ "$major" -eq 3 ]] && [[ "$minor" -ge 7 ]]; then
            score=$((score + 50))
        fi

        # Penalize alpha/beta/rc versions heavily
        if [[ "$version" =~ (a|b|rc) ]]; then
            score=$((score - 1000))
        fi

        # Prefer /usr/bin over /usr/local (more stable on macOS)
        if [[ "$py_cmd" == "/usr/bin/python3" ]]; then
            score=$((score + 10))
        fi

        # Track best candidate
        if [[ $score -gt $best_score ]]; then
            best_score=$score
            best_python="$py_cmd"
            best_version="$version"
        fi
    done

    if [[ -n "$best_python" ]]; then
        export PYTHON_CMD="$best_python"
        print_success "Python is installed ($best_version)"

        # Warn about alpha/beta versions
        if [[ "$best_version" =~ (a|b|rc) ]]; then
            print_warning "Using pre-release Python version - some packages may fail to install"
            print_info "Consider installing a stable Python version for better compatibility"
        fi

        # Check for pip
        if $best_python -m pip --version &> /dev/null; then
            print_success "pip is available"
            return 0
        else
            print_warning "pip not found - Python packages cannot be installed"
            return 1
        fi
    else
        print_warning "Python not found"
        print_info "The parallel agent (parallel_agent.py) requires Python 3.9+"
        print_info ""
        print_info "To install Python:"
        if [[ "$PLATFORM" == "macos" ]]; then
            print_info "  macOS: brew install python3"
        else
            print_info "  Linux: Use your package manager (apt install python3, dnf install python3, etc.)"
        fi
        return 1
    fi
}

# Install Node.js (required for some CLIs)
install_node() {
    print_step "Checking for Node.js..."

    if command_exists node; then
        local node_version
        node_version=$(node --version)
        print_success "Node.js is installed ($node_version)"
    else
        print_warning "Node.js not found"

        if [[ "$PLATFORM" == "macos" ]]; then
            if command_exists brew && prompt_yes_no "Install Node.js via Homebrew?"; then
                print_step "Installing Node.js..."
                brew install node
                print_success "Node.js installed"
            else
                print_warning "Please install Node.js manually from https://nodejs.org"
            fi
        elif [[ "$PLATFORM" == "linux" ]]; then
            echo ""
            echo -e "${BOLD}Node.js Installation Options:${NC}"
            echo "  1. Use system package manager"
            echo "  2. Use NodeSource repository (recommended for latest LTS)"
            echo "  3. Skip (install manually later)"
            echo ""
            read -r -p "Choose option [1/2/3]: " node_choice

            case $node_choice in
                1)
                    print_step "Installing Node.js via $PKG_MANAGER..."
                    case "$PKG_MANAGER" in
                        apt)
                            sudo apt-get install -y nodejs npm
                            ;;
                        dnf)
                            sudo dnf install -y nodejs npm
                            ;;
                        yum)
                            sudo yum install -y nodejs npm
                            ;;
                        pacman)
                            sudo pacman -S --noconfirm nodejs npm
                            ;;
                        zypper)
                            sudo zypper install -y nodejs npm
                            ;;
                        *)
                            print_error "Package manager not supported for Node.js installation"
                            ;;
                    esac
                    print_success "Node.js installed"
                    ;;
                2)
                    print_step "Installing Node.js via NodeSource..."
                    if [[ "$PKG_MANAGER" == "apt" ]]; then
                        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
                        sudo apt-get install -y nodejs
                    elif [[ "$PKG_MANAGER" == "dnf" || "$PKG_MANAGER" == "yum" ]]; then
                        curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
                        sudo "$PKG_MANAGER" install -y nodejs
                    else
                        print_warning "NodeSource not available for $PKG_MANAGER"
                        print_info "Please install Node.js manually from https://nodejs.org"
                    fi
                    ;;
                *)
                    print_warning "Node.js not installed - some CLI tools may not work"
                    ;;
            esac
        fi
    fi
}

# Install Claude Code CLI
install_claude() {
    if [[ "$ENABLE_CLAUDE" == false ]]; then
        print_info "Claude CLI is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for Claude Code CLI..."

    if command_exists claude; then
        print_success "Claude Code CLI is installed"
        claude --version 2> /dev/null || true
    else
        print_warning "Claude Code CLI not found"
        echo ""
        echo -e "${BOLD}Claude Code CLI Installation Options:${NC}"
        echo "  1. npm install -g @anthropic-ai/claude-code"
        echo "  2. Download from https://claude.ai/code"
        echo ""

        if prompt_yes_no "Install Claude Code CLI via npm?"; then
            if command_exists npm; then
                print_step "Installing Claude Code CLI..."
                npm install -g @anthropic-ai/claude-code
                print_success "Claude Code CLI installed"
            else
                print_error "npm not found. Please install Node.js first."
                return 1
            fi
        else
            print_warning "Claude Code CLI not installed"
            if prompt_yes_no "Disable Claude in service configuration?"; then
                ENABLE_CLAUDE=false
            fi
        fi
    fi
}

# Install Gemini CLI
install_gemini() {
    if [[ "$ENABLE_GEMINI" == false ]]; then
        print_info "Gemini CLI is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for Gemini CLI..."

    if command_exists gemini; then
        print_success "Gemini CLI is installed"
    else
        print_warning "Gemini CLI not found"
        echo ""
        echo -e "${BOLD}Gemini CLI Installation Options:${NC}"
        echo "  1. npm install -g @google/gemini-cli"
        echo "  2. See https://github.com/google-gemini/gemini-cli"
        echo ""

        if prompt_yes_no "Install Gemini CLI via npm?"; then
            if command_exists npm; then
                print_step "Installing Gemini CLI..."
                npm install -g @google/gemini-cli
                print_success "Gemini CLI installed"
            else
                print_error "npm not found. Please install Node.js first."
                return 1
            fi
        else
            print_warning "Gemini CLI not installed"
            if prompt_yes_no "Disable Gemini in service configuration?"; then
                ENABLE_GEMINI=false
            fi
        fi
    fi
}

# Install Codex CLI
install_codex() {
    if [[ "$ENABLE_CODEX" == false ]]; then
        print_info "Codex CLI is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for Codex CLI..."

    if command_exists codex; then
        print_success "Codex CLI is installed"
        codex --version 2> /dev/null || true
    else
        print_warning "Codex CLI not found"
        echo ""
        echo -e "${BOLD}Codex CLI Installation Options:${NC}"
        echo "  1. npm install -g @openai/codex"
        if [[ "$PLATFORM" == "macos" ]]; then
            echo "  2. brew install --cask codex"
        else
            echo "  2. See https://github.com/openai/codex"
        fi
        echo ""

        if prompt_yes_no "Install Codex CLI via npm?"; then
            if command_exists npm; then
                print_step "Installing Codex CLI..."
                npm install -g @openai/codex
                print_success "Codex CLI installed"
            else
                print_error "npm not found. Please install Node.js first."
                return 1
            fi
        else
            print_warning "Codex CLI not installed"
            if prompt_yes_no "Disable Codex in service configuration?"; then
                ENABLE_CODEX=false
            fi
        fi
    fi
}

# Install GitHub CLI
install_github_cli() {
    # Auto-detect: skip if already installed or disabled
    if [[ "$ENABLE_GH" == "auto" ]]; then
        if command_exists gh; then
            print_info "GitHub CLI (gh) is installed - enabling"
            ENABLE_GH=true
            return 0
        else
            print_info "GitHub CLI (gh) not found - skipping (auto-detect)"
            ENABLE_GH=false
            return 0
        fi
    fi

    if [[ "$ENABLE_GH" == false ]]; then
        print_info "GitHub CLI is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for GitHub CLI (gh)..."

    if command_exists gh; then
        print_success "GitHub CLI (gh) is installed"
        gh --version 2> /dev/null || true
    else
        print_warning "GitHub CLI (gh) not found"
        echo ""
        echo -e "${BOLD}GitHub CLI Installation Options:${NC}"
        case "$PLATFORM" in
            macos)
                echo "  brew install gh"
                ;;
            linux)
                case "$PKG_MANAGER" in
                    apt)
                        echo "  sudo apt install gh"
                        ;;
                    dnf | yum)
                        echo "  sudo dnf install gh"
                        ;;
                    pacman)
                        echo "  sudo pacman -S github-cli"
                        ;;
                    *)
                        echo "  See https://cli.github.com/manual/installation"
                        ;;
                esac
                ;;
        esac
        echo ""

        if prompt_yes_no "Install GitHub CLI now?"; then
            case "$PLATFORM" in
                macos)
                    if command_exists brew; then
                        print_step "Installing GitHub CLI via Homebrew..."
                        brew install gh
                        print_success "GitHub CLI installed"
                    else
                        print_error "Homebrew not found. Please install Homebrew first."
                        return 1
                    fi
                    ;;
                linux)
                    case "$PKG_MANAGER" in
                        apt)
                            print_step "Installing GitHub CLI via apt..."
                            sudo apt update && sudo apt install -y gh
                            print_success "GitHub CLI installed"
                            ;;
                        dnf | yum)
                            print_step "Installing GitHub CLI via $PKG_MANAGER..."
                            sudo "$PKG_MANAGER" install -y gh
                            print_success "GitHub CLI installed"
                            ;;
                        pacman)
                            print_step "Installing GitHub CLI via pacman..."
                            sudo pacman -S --noconfirm github-cli
                            print_success "GitHub CLI installed"
                            ;;
                        *)
                            print_error "Package manager not supported. Please install manually: https://cli.github.com/manual/installation"
                            return 1
                            ;;
                    esac
                    ;;
            esac
        else
            print_warning "GitHub CLI not installed"
            if prompt_yes_no "Disable GitHub CLI in service configuration?"; then
                ENABLE_GH=false
            fi
        fi
    fi
}

# Install GitLab CLI
install_gitlab_cli() {
    # Auto-detect: skip if already installed or disabled
    if [[ "$ENABLE_GLAB" == "auto" ]]; then
        if command_exists glab; then
            print_info "GitLab CLI (glab) is installed - enabling"
            ENABLE_GLAB=true
            return 0
        else
            print_info "GitLab CLI (glab) not found - skipping (auto-detect)"
            ENABLE_GLAB=false
            return 0
        fi
    fi

    if [[ "$ENABLE_GLAB" == false ]]; then
        print_info "GitLab CLI is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for GitLab CLI (glab)..."

    if command_exists glab; then
        print_success "GitLab CLI (glab) is installed"
        glab --version 2> /dev/null || true
    else
        print_warning "GitLab CLI (glab) not found"
        echo ""
        echo -e "${BOLD}GitLab CLI Installation Options:${NC}"
        case "$PLATFORM" in
            macos)
                echo "  brew install glab"
                ;;
            linux)
                case "$PKG_MANAGER" in
                    apt)
                        echo "  sudo apt install glab"
                        ;;
                    dnf | yum)
                        echo "  sudo dnf install glab"
                        ;;
                    pacman)
                        echo "  sudo pacman -S glab"
                        ;;
                    *)
                        echo "  See https://gitlab.com/gitlab-org/cli"
                        ;;
                esac
                ;;
        esac
        echo ""

        if prompt_yes_no "Install GitLab CLI now?"; then
            case "$PLATFORM" in
                macos)
                    if command_exists brew; then
                        print_step "Installing GitLab CLI via Homebrew..."
                        brew install glab
                        print_success "GitLab CLI installed"
                    else
                        print_error "Homebrew not found. Please install Homebrew first."
                        return 1
                    fi
                    ;;
                linux)
                    case "$PKG_MANAGER" in
                        apt)
                            print_step "Installing GitLab CLI via apt..."
                            sudo apt update && sudo apt install -y glab
                            print_success "GitLab CLI installed"
                            ;;
                        dnf | yum)
                            print_step "Installing GitLab CLI via $PKG_MANAGER..."
                            sudo "$PKG_MANAGER" install -y glab
                            print_success "GitLab CLI installed"
                            ;;
                        pacman)
                            print_step "Installing GitLab CLI via pacman..."
                            sudo pacman -S --noconfirm glab
                            print_success "GitLab CLI installed"
                            ;;
                        *)
                            print_error "Package manager not supported. Please install manually: https://gitlab.com/gitlab-org/cli"
                            return 1
                            ;;
                    esac
                    ;;
            esac
        else
            print_warning "GitLab CLI not installed"
            if prompt_yes_no "Disable GitLab CLI in service configuration?"; then
                ENABLE_GLAB=false
            fi
        fi
    fi
}

# Check for jq (required by git_ops.sh)
check_jq() {
    print_step "Checking for jq (required by git_ops.sh)..."

    if command_exists jq; then
        print_success "jq is installed"
    else
        print_warning "jq not found"
        echo ""
        echo -e "${BOLD}jq Installation Options:${NC}"
        case "$PLATFORM" in
            macos)
                echo "  brew install jq"
                ;;
            linux)
                case "$PKG_MANAGER" in
                    apt)
                        echo "  sudo apt install jq"
                        ;;
                    dnf | yum)
                        echo "  sudo dnf install jq"
                        ;;
                    pacman)
                        echo "  sudo pacman -S jq"
                        ;;
                    zypper)
                        echo "  sudo zypper install jq"
                        ;;
                    *)
                        echo "  See https://stedolan.github.io/jq/"
                        ;;
                esac
                ;;
        esac
        echo ""

        if prompt_yes_no "Install jq now?"; then
            case "$PLATFORM" in
                macos)
                    if command_exists brew; then
                        print_step "Installing jq via Homebrew..."
                        brew install jq
                        print_success "jq installed"
                    else
                        print_error "Homebrew not found."
                        return 1
                    fi
                    ;;
                linux)
                    case "$PKG_MANAGER" in
                        apt)
                            print_step "Installing jq via apt..."
                            sudo apt update && sudo apt install -y jq
                            print_success "jq installed"
                            ;;
                        dnf | yum)
                            print_step "Installing jq via $PKG_MANAGER..."
                            sudo "$PKG_MANAGER" install -y jq
                            print_success "jq installed"
                            ;;
                        pacman)
                            print_step "Installing jq via pacman..."
                            sudo pacman -S --noconfirm jq
                            print_success "jq installed"
                            ;;
                        zypper)
                            print_step "Installing jq via zypper..."
                            sudo zypper install -y jq
                            print_success "jq installed"
                            ;;
                        *)
                            print_error "Package manager not supported."
                            return 1
                            ;;
                    esac
                    ;;
            esac
        else
            print_warning "jq not installed - git_ops.sh may have limited functionality"
        fi
    fi
}

# Ensure rsync is available — the config/skill deploy in deploy.sh + common.sh
# uses it (the config-tree copy and the skill copy). Best-effort auto-install;
# non-fatal: deploy_home_skills already has a cp fallback, but the config-tree
# rsync (with --exclude) prefers rsync, so we try to provide it. Every path
# returns 0 so the unguarded caller is never aborted under set -e.
check_rsync() {
    if command_exists rsync; then
        print_success "rsync is installed"
        return 0
    fi

    print_step "Installing rsync (used by config/skill deploy)..."

    case "$PLATFORM" in
        macos)
            if command_exists brew && brew install rsync; then
                print_success "rsync installed"
                return 0
            fi
            ;;
        linux)
            case "$PKG_MANAGER" in
                apt)
                    if sudo apt-get update -qq && sudo apt-get install -y -qq rsync; then
                        print_success "rsync installed"
                        return 0
                    fi
                    ;;
                dnf | yum)
                    if sudo "$PKG_MANAGER" install -y rsync; then
                        print_success "rsync installed"
                        return 0
                    fi
                    ;;
                pacman)
                    if sudo pacman -S --noconfirm rsync; then
                        print_success "rsync installed"
                        return 0
                    fi
                    ;;
                zypper)
                    if sudo zypper install -y rsync; then
                        print_success "rsync installed"
                        return 0
                    fi
                    ;;
            esac
            ;;
    esac

    print_warning "Could not install rsync automatically; skill deploy will fall back to cp. Install rsync for the full config-tree sync."
    return 0
}

# Install the cursor-agent CLI (headless Cursor agent used by parallel_agent.py)
check_cursor() {
    if [[ "$ENABLE_CURSOR" == false ]]; then
        print_info "Cursor is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for cursor-agent CLI..."

    if command_exists cursor-agent || [[ -f "$HOME/.local/bin/cursor-agent" ]]; then
        print_success "cursor-agent is installed"
        return 0
    fi

    print_warning "cursor-agent CLI not found"
    echo ""
    echo -e "${BOLD}cursor-agent Installation:${NC}"
    echo "  curl https://cursor.com/install -fsS | bash"
    echo ""

    if prompt_yes_no "Install cursor-agent now?"; then
        if curl https://cursor.com/install -fsS | bash; then
            if command_exists cursor-agent || [[ -f "$HOME/.local/bin/cursor-agent" ]]; then
                print_success "cursor-agent installed"
                print_info "Authenticate with: cursor-agent login  (or set CURSOR_API_KEY)"
            else
                print_warning "cursor-agent installed but not yet on PATH (restart your shell)"
            fi
        else
            print_warning "cursor-agent installation failed"
            if prompt_yes_no "Disable Cursor in service configuration?"; then
                ENABLE_CURSOR=false
            fi
        fi
    else
        print_warning "cursor-agent not installed"
        if prompt_yes_no "Disable Cursor in service configuration?"; then
            ENABLE_CURSOR=false
        fi
    fi
}

# Ensure the uv Python tool installer is present (graphify's install prerequisite).
# Idempotent and existence-guarded (Principle V): no-op if uv is already available,
# even when it lives at ~/.local/bin and is not yet on this shell's PATH. Prefers a
# package manager, falling back to a portable pip --user install (Python is a prereq).
check_uv() {
    if command_exists uv || [[ -x "$HOME/.local/bin/uv" ]]; then
        print_success "uv is installed"
        return 0
    fi

    print_step "Installing uv (Python tool installer)..."

    case "$PLATFORM" in
        macos)
            if command_exists brew && brew install uv; then
                print_success "uv installed via Homebrew"
                return 0
            fi
            ;;
        linux)
            # Only pacman reliably packages uv; apt/dnf/yum/zypper do not, so those
            # fall through to the portable pip path below.
            if [[ "$PKG_MANAGER" == "pacman" ]] && sudo pacman -S --noconfirm uv; then
                print_success "uv installed via pacman"
                return 0
            fi
            ;;
    esac

    # Portable fallback 1: official standalone installer. Drops a self-contained uv
    # binary into ~/.local/bin (already on the framework PATH) with no Python/pip,
    # so it works on PEP 668 externally-managed interpreters (default Debian/Ubuntu,
    # Homebrew Python) where `pip install --user` is blocked. Same curl|sh idiom the
    # framework already uses for cursor-agent.
    if command_exists curl && curl -LsSf https://astral.sh/uv/install.sh | sh; then
        if command_exists uv || [[ -x "$HOME/.local/bin/uv" ]]; then
            print_success "uv installed via the official installer"
            return 0
        fi
    fi

    # Portable fallback 2: pip --user, for environments that have Python 3 but no
    # curl. May fail on PEP 668 interpreters; that is handled by the caller (warn
    # and continue), since graphify is an optional capability.
    if check_python; then
        local python_cmd="${PYTHON_CMD:-python3}"
        if $python_cmd -m pip install --user --prefer-binary uv; then
            print_success "uv installed via pip --user"
            return 0
        fi
    fi

    print_warning "Could not install uv automatically; see https://docs.astral.sh/uv/ to enable graphify"
    return 1
}

# Install the graphify knowledge-graph CLI (PyPI package 'graphifyy', command 'graphify').
# Default-enabled service. Idempotent and existence-guarded (Principle V): installs only
# when graphifyy is absent. Never aborts bootstrap — every failure path warns and returns 0
# (graphify is an optional capability; FR-006 / SC-005).
install_graphify() {
    if [[ "$ENABLE_GRAPHIFY" == false ]]; then
        print_info "graphify is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for graphify..."

    if ! check_uv; then
        print_warning "uv is required to install graphify - skipping (re-run ./bootstrap.sh --enable-graphify once uv is available)"
        return 0
    fi

    # Resolve uv: it may have just been pip-installed to ~/.local/bin and not yet
    # be on this shell's PATH.
    local uv_bin
    if command_exists uv; then
        uv_bin="uv"
    elif [[ -x "$HOME/.local/bin/uv" ]]; then
        uv_bin="$HOME/.local/bin/uv"
    else
        print_warning "uv not found on PATH after install - skipping graphify"
        return 0
    fi

    # Existence guard: only install when graphifyy is absent (idempotent).
    if "$uv_bin" tool list 2> /dev/null | grep -q '^graphifyy'; then
        print_success "graphify (graphifyy) is already installed"
        return 0
    fi

    print_step "Installing graphify (graphifyy) via uv..."
    if "$uv_bin" tool install graphifyy; then
        print_success "graphify installed successfully"
    else
        print_warning "Failed to install graphifyy via uv - continuing (graphify will be unavailable)"
    fi
    return 0
}

# Sync the home Python runtime via uv (replaces pip install --user for parallel_agent deps).
# Reads deployed services.yml for optional dependency groups, runs uv sync, optionally
# installs Playwright Chromium for smoke, and deploys ~/.local/bin/manifest wrapper.
uv_sync_home_runtime() {
    local target_dir="${TARGET_DIR:-$HOME/.claude}"
    local uv_bin=""
    if command_exists uv; then
        uv_bin="$(command -v uv)"
    elif [[ -x "$HOME/.local/bin/uv" ]]; then
        uv_bin="$HOME/.local/bin/uv"
    else
        print_warning "uv not found — skipping home runtime sync"
        return 0
    fi
    UV_BIN="$uv_bin"

    local -a group_flags=()
    local services_yml="$target_dir/config/services.yml"
    if [[ -f "$services_yml" ]]; then
        if python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print('1' if d.get('services',{}).get('smoke',{}).get('enabled') else '0')" "$services_yml" | grep -q 1; then
            group_flags+=(--group smoke)
        fi
        if python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print('1' if d.get('services',{}).get('browser_use',{}).get('enabled') else '0')" "$services_yml" | grep -q 1; then
            group_flags+=(--group smoke --group smoke-agent)
        fi
        if python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print('1' if d.get('services',{}).get('claude',{}).get('enabled') else '0')" "$services_yml" | grep -q 1; then
            group_flags+=(--group claude)
        fi
    fi

    print_step "Syncing home Python runtime (uv)..."
    if ! "$uv_bin" sync --project "$target_dir" "${group_flags[@]}"; then
        print_warning "uv sync failed — parallel agent may be unavailable"
        return 0
    fi

    if [[ " ${group_flags[*]} " == *" smoke "* ]]; then
        "$target_dir/.venv/bin/playwright" install chromium || print_warning "playwright install chromium failed"
    fi

    mkdir -p "$HOME/.local/bin"
    cp "$SCRIPT_DIR/configs/claude/scripts/manifest-cli.sh" "$HOME/.local/bin/manifest"
    chmod +x "$HOME/.local/bin/manifest"
    print_success "Home runtime synced; manifest CLI at ~/.local/bin/manifest"
}
