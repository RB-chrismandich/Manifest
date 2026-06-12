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
                    eval "$(/opt/homebrew/bin/brew shellenv)"
                fi
                # Add Homebrew to PATH for Intel Mac
                if [[ -f "/usr/local/bin/brew" ]]; then
                    eval "$(/usr/local/bin/brew shellenv)"
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

# Install Python dependencies for parallel_agent.py
install_python_dependencies() {
    if ! check_python; then
        return 0 # Skip if Python not available, non-fatal
    fi

    # Use PYTHON_CMD from check_python
    local python_cmd="${PYTHON_CMD:-python3}"

    local requirements_file="$TARGET_DIR/scripts/requirements.txt"

    if [[ ! -f "$requirements_file" ]]; then
        print_warning "requirements.txt not found at $requirements_file"
        return 0
    fi

    print_step "Installing Python dependencies for parallel_agent.py..."
    print_info "Using: $python_cmd"

    # Try to install with --user flag and prefer binary wheels
    if $python_cmd -m pip install --user --prefer-binary -q -r "$requirements_file" 2>&1; then
        print_success "Python dependencies installed"
    else
        print_warning "Failed to install Python dependencies"
        print_info "Some packages may require compilation or may not support this Python version"
        print_info "You can install manually later with:"
        print_info "  $python_cmd -m pip install --prefer-binary -r $requirements_file"
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
                        sudo $PKG_MANAGER install -y nodejs
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

# Install Cursor (if needed for cursor agent)
check_cursor() {
    if [[ "$ENABLE_CURSOR" == false ]]; then
        print_info "Cursor is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for Cursor IDE..."

    local cursor_found=false

    # Check for Cursor on macOS
    if [[ "$PLATFORM" == "macos" ]]; then
        if [[ -d "/Applications/Cursor.app" ]] || command_exists cursor; then
            cursor_found=true
        fi
    # Check for Cursor on Linux
    elif [[ "$PLATFORM" == "linux" ]]; then
        if command_exists cursor; then
            cursor_found=true
        elif [[ -d "$HOME/.local/share/cursor" ]] || [[ -d "/opt/cursor" ]]; then
            cursor_found=true
        elif [[ -f "$HOME/.local/bin/cursor" ]]; then
            cursor_found=true
        fi
    fi

    if [[ "$cursor_found" == true ]]; then
        print_success "Cursor is installed"
    else
        print_warning "Cursor IDE not found"
        echo ""
        echo -e "${BOLD}Cursor IDE Installation:${NC}"
        echo "  Download from: https://cursor.sh"

        if [[ "$PLATFORM" == "linux" ]]; then
            echo ""
            echo "  Linux: Download the AppImage or .deb package"
            echo "  After download, make it executable and add to PATH"
        fi
        echo ""

        if prompt_yes_no "Open Cursor download page in browser?"; then
            open_url "https://cursor.sh"
            echo ""
            print_info "After installing Cursor, run this script again to continue setup"
        else
            print_warning "Cursor not installed"
            if prompt_yes_no "Disable Cursor in service configuration?"; then
                ENABLE_CURSOR=false
            fi
        fi
    fi
}

# Install browser-use E2E testing library and Playwright browsers
install_browser_use() {
    if [[ "$ENABLE_BROWSER_USE" == false ]]; then
        print_info "browser-use is disabled - skipping installation"
        return 0
    fi

    print_step "Checking for browser-use..."

    if ! check_python; then
        print_warning "Python 3 is required to install browser-use - skipping"
        return 0
    fi

    local python_cmd="${PYTHON_CMD:-python3}"

    if $python_cmd -c "import browser_use" &> /dev/null; then
        print_success "browser-use is already installed"
    else
        print_step "Installing browser-use Python package..."
        if $python_cmd -m pip install --user --prefer-binary browser-use; then
            print_success "browser-use package installed successfully"
        else
            print_error "Failed to install browser-use package"
            return 1
        fi
    fi

    # Install Playwright browser binaries
    print_step "Installing Playwright browsers..."
    if $python_cmd -m playwright install chromium; then
        print_success "Playwright browsers installed successfully"
    else
        print_warning "Failed to install Playwright browsers via 'playwright install chromium'. You may need to run this manually."
    fi
}

