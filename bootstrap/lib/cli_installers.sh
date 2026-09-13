# shellcheck shell=bash
# CLI installer functions sourced by install.sh.
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
