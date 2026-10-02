# shellcheck shell=bash
# Optional CLI and support command functions sourced by install.sh.
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

# Install the cursor-agent CLI (retained single-provider integration; see model_policy.yml)
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

    print_warning "cursor-agent CLI not found; automatic install is unavailable"
    print_info "Install cursor-agent with the vendor's verified package, then rerun bootstrap."
    if prompt_yes_no "Disable Cursor in service configuration?"; then
        ENABLE_CURSOR=false
    fi
}

# Install the Devin CLI (Cognition's headless coding agent, `devin`).
# Opt-in: Homebrew is the only package-manager path this bootstrap verifies.
check_devin() {
    if [[ "${ENABLE_DEVIN:-false}" == false ]]; then
        print_info "Devin is disabled - skipping installation"
        return 0
    fi
    print_step "Checking for Devin CLI..."
    if command_exists devin || [[ -x "$HOME/.local/bin/devin" ]]; then
        print_success "Devin CLI is installed"
        return 0
    fi
    if ! command_exists brew; then
        print_warning "Devin CLI requires a verified manual install on this platform"
        if prompt_yes_no "Disable Devin in service configuration?"; then ENABLE_DEVIN=false; fi
        return 0
    fi
    if prompt_yes_no "Install Devin CLI with Homebrew now?"; then
        brew install --cask devin-cli
    fi
    if command_exists devin || [[ -x "$HOME/.local/bin/devin" ]]; then
        print_success "Devin CLI installed"
        print_info "Authenticate with: devin auth login"
    else
        print_warning "Devin CLI not installed"
        if prompt_yes_no "Disable Devin in service configuration?"; then ENABLE_DEVIN=false; fi
    fi
}

# Verified uv release bootstrap is isolated so this installer remains focused
# on platform package management and harness installation.
# shellcheck source=bootstrap/lib/verified_uv.sh
source "$(dirname "${BASH_SOURCE[0]}")/verified_uv.sh"

# The pinned-apm-wheel install path was removed by spec 674 Phase 5 (T5.4).
# It existed to install the tool that owned ~/.claude/skills; skills now ship
# as plugin bundles and apm owns nothing. Its integrity suites
# (apm_binary_integrity, apm_supply_chain, apm_upgrade_gate) were retired in
# the same commit -- keeping the code without them would have left an
# unguarded network install path, which is strictly worse than either.
# Rollback does NOT need it: apm_ungate_domain.sh and sync-skills.sh invoke
# no apm binary (verified, not assumed).

# Read the three optional-group toggles out of the deployed services.yml in ONE
# probe. Echoes "<smoke> <browser_use> <claude>" as 0/1 flags; returns non-zero
# when no interpreter could parse the file at all.
#
# Three separate `python3 -c … | grep -q 1` probes used to make a probe failure
# (system python3 without PyYAML) indistinguishable from "service disabled": an
# enabled smoke/browser-use service silently got no deps and only failed later,
