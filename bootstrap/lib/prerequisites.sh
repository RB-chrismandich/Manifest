# shellcheck shell=bash
# Runtime prerequisite functions sourced by install.sh.
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
        print_info "Python 3.9+ is required by several Manifest scripts"
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
                    print_warning "NodeSource setup is not run automatically without a committed checksum"
                    print_info "Install Node.js manually from https://nodejs.org"
                    ;;
                *)
                    print_warning "Node.js not installed - some CLI tools may not work"
                    ;;
            esac
        fi
    fi
}
