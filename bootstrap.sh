#!/bin/bash
# Bootstrap script for AI Agent Support Framework
# Installs dependencies, deploys configurations, and sets up authentication
# Supports: macOS (Intel/Apple Silicon) and Linux (Debian/Ubuntu, RHEL/Fedora, Arch)
#
# Usage: ./bootstrap.sh [options]
#
# Service toggles:
#   --enable-claude     Enable Claude CLI (default: enabled)
#   --disable-claude    Disable Claude CLI
#   --enable-gemini     Enable Gemini CLI (default: enabled)
#   --disable-gemini    Disable Gemini CLI
#   --enable-cursor     Enable Cursor agent (default: enabled)
#   --disable-cursor    Disable Cursor agent
#   --enable-gh         Enable GitHub CLI (default: auto-detect)
#   --disable-gh        Disable GitHub CLI
#   --enable-glab       Enable GitLab CLI (default: auto-detect)
#   --disable-glab      Disable GitLab CLI
#
# Other options:
#   --skip-install      Skip CLI tool installation
#   --skip-auth         Skip authentication checks
#   --force             Overwrite existing ~/.claude without prompting
#   --reconfigure       Only update service toggles (skip full setup)

set -e

# Cleanup function to restore cursor on exit/interrupt
cleanup() {
    if command -v tput &> /dev/null; then
        tput cnorm 2> /dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.claude"
CURSOR_TARGET_DIR="$HOME/.cursor"
GEMINI_TARGET_DIR="$HOME/.gemini"
SERVICES_CONFIG="$TARGET_DIR/config/services.yml"

# Detect platform
PLATFORM="unknown"
export DISTRO=""
PKG_MANAGER=""

detect_platform() {
    case "$(uname -s)" in
        Darwin)
            PLATFORM="macos"
            ;;
        Linux)
            PLATFORM="linux"
            # Detect Linux distribution
            if [[ -f /etc/os-release ]]; then
                . /etc/os-release
                DISTRO="$ID"
            elif [[ -f /etc/debian_version ]]; then
                DISTRO="debian"
            elif [[ -f /etc/redhat-release ]]; then
                DISTRO="rhel"
            fi

            # Detect package manager
            if command -v apt-get &> /dev/null; then
                PKG_MANAGER="apt"
            elif command -v dnf &> /dev/null; then
                PKG_MANAGER="dnf"
            elif command -v yum &> /dev/null; then
                PKG_MANAGER="yum"
            elif command -v pacman &> /dev/null; then
                PKG_MANAGER="pacman"
            elif command -v zypper &> /dev/null; then
                PKG_MANAGER="zypper"
            fi
            ;;
        *)
            PLATFORM="unknown"
            ;;
    esac
}

# Cross-platform browser open
open_url() {
    local url="$1"
    case "$PLATFORM" in
        macos)
            open "$url"
            ;;
        linux)
            if command -v xdg-open &> /dev/null; then
                xdg-open "$url"
            elif command -v gnome-open &> /dev/null; then
                gnome-open "$url"
            elif command -v kde-open &> /dev/null; then
                kde-open "$url"
            else
                print_warning "Could not open browser. Please visit: $url"
                return 1
            fi
            ;;
        *)
            print_warning "Could not open browser. Please visit: $url"
            return 1
            ;;
    esac
}

# Initialize platform detection
detect_platform

# Detect timeout command (timeout on Linux, gtimeout on macOS via coreutils)
TIMEOUT_CMD=""
if command -v timeout &> /dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &> /dev/null; then
    TIMEOUT_CMD="gtimeout"
fi

# Flags
SKIP_INSTALL=false
SKIP_AUTH=false
FORCE=false
RECONFIGURE=false

# Service toggles (default: all enabled, gh/glab auto-detect)
ENABLE_CLAUDE=true
ENABLE_GEMINI=true
ENABLE_CURSOR=true
ENABLE_GH="auto"
ENABLE_GLAB="auto"

# Track if user explicitly set toggles
CLAUDE_SET=false
GEMINI_SET=false
CURSOR_SET=false
GH_SET=false
GLAB_SET=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --enable-claude)
            ENABLE_CLAUDE=true
            CLAUDE_SET=true
            shift
            ;;
        --disable-claude)
            ENABLE_CLAUDE=false
            CLAUDE_SET=true
            shift
            ;;
        --enable-gemini)
            ENABLE_GEMINI=true
            GEMINI_SET=true
            shift
            ;;
        --disable-gemini)
            ENABLE_GEMINI=false
            GEMINI_SET=true
            shift
            ;;
        --enable-cursor)
            ENABLE_CURSOR=true
            CURSOR_SET=true
            shift
            ;;
        --disable-cursor)
            ENABLE_CURSOR=false
            CURSOR_SET=true
            shift
            ;;
        --enable-gh)
            ENABLE_GH=true
            GH_SET=true
            shift
            ;;
        --disable-gh)
            ENABLE_GH=false
            GH_SET=true
            shift
            ;;
        --enable-glab)
            ENABLE_GLAB=true
            GLAB_SET=true
            shift
            ;;
        --disable-glab)
            ENABLE_GLAB=false
            GLAB_SET=true
            shift
            ;;
        --skip-install)
            SKIP_INSTALL=true
            shift
            ;;
        --skip-auth)
            SKIP_AUTH=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --reconfigure)
            RECONFIGURE=true
            shift
            ;;
        -h | --help)
            echo "AI Agent Support Framework Bootstrap"
            echo "Supports: macOS (Intel/Apple Silicon), Linux (Debian, RHEL, Arch, etc.)"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Service Toggles:"
            echo "  --enable-claude     Enable Claude CLI (default: enabled)"
            echo "  --disable-claude    Disable Claude CLI"
            echo "  --enable-gemini     Enable Gemini CLI (default: enabled)"
            echo "  --disable-gemini    Disable Gemini CLI"
            echo "  --enable-cursor     Enable Cursor agent (default: enabled)"
            echo "  --disable-cursor    Disable Cursor agent"
            echo "  --enable-gh         Enable GitHub CLI (default: auto-detect)"
            echo "  --disable-gh        Disable GitHub CLI"
            echo "  --enable-glab       Enable GitLab CLI (default: auto-detect)"
            echo "  --disable-glab      Disable GitLab CLI"
            echo ""
            echo "Other Options:"
            echo "  --skip-install      Skip CLI tool installation"
            echo "  --skip-auth         Skip authentication checks"
            echo "  --force             Overwrite existing ~/.claude without prompting"
            echo "  --reconfigure       Only update service toggles (skip full setup)"
            echo ""
            echo "Examples:"
            echo "  $0                              # Full setup with all services"
            echo "  $0 --disable-cursor             # Setup without Cursor"
            echo "  $0 --enable-gh --enable-glab    # Explicitly enable Git CLIs"
            echo "  $0 --reconfigure --disable-gemini  # Just disable Gemini"
            echo "  $0 --skip-auth                  # Setup without authentication checks"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Helper functions
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

    # Print question in bold, options in cyan
    echo -ne "${BOLD}${question}${NC} ${CYAN}${prompt_suffix}${NC}: "

    read -r response
    response="${response:-$default}"

    # Check for yes (Y, y, Yes, yes, YES)
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
    local spinner=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local spin_idx=0

    # Check for tput availability
    local has_tput=false
    if command -v tput &> /dev/null; then
        has_tput=true
    fi

    # Hide cursor
    if $has_tput; then
        tput civis 2> /dev/null || true
    fi

    # Start command in background
    eval "$cmd" &
    pid=$!

    # Show spinner while command runs
    while kill -0 "$pid" 2> /dev/null; do
        spin_idx=$(((spin_idx + 1) % ${#spinner[@]}))
        printf "\r${CYAN}${spinner[$spin_idx]}${NC} %s..." "$msg"
        sleep 0.1
    done

    # Wait for command to complete and get exit code
    wait "$pid"
    local exit_code=$?

    # Restore cursor
    if $has_tput; then
        tput cnorm 2> /dev/null || true
    fi

    # Clear spinner line
    printf "\r\033[K"

    return $exit_code
}

# Parse service configuration using awk (single pass)
parse_services_config() {
    FILE_CLAUDE=""
    FILE_GEMINI=""
    FILE_CURSOR=""
    FILE_GH=""
    FILE_GLAB=""

    if [[ -f "$SERVICES_CONFIG" ]]; then
        local config_settings
        config_settings=$(awk '
            BEGIN { section=""; subsection="" }
            /^[[:space:]]*claude:/ { section="claude"; subsection="" }
            /^[[:space:]]*gemini:/ { section="gemini"; subsection="" }
            /^[[:space:]]*cursor:/ { section="cursor"; subsection="" }
            /^[[:space:]]*git_cli:/ { section="git_cli"; subsection="" }
            /^[[:space:]]*github:/ { if (section == "git_cli") subsection="github" }
            /^[[:space:]]*gitlab:/ { if (section == "git_cli") subsection="gitlab" }
            /^[[:space:]]*enabled:[[:space:]]*true/ {
                if (section == "claude") print "FILE_CLAUDE=true;"
                if (section == "gemini") print "FILE_GEMINI=true;"
                if (section == "cursor") print "FILE_CURSOR=true;"
                if (section == "git_cli" && subsection == "github") print "FILE_GH=true;"
                if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=true;"
            }
            /^[[:space:]]*enabled:[[:space:]]*false/ {
                if (section == "claude") print "FILE_CLAUDE=false;"
                if (section == "gemini") print "FILE_GEMINI=false;"
                if (section == "cursor") print "FILE_CURSOR=false;"
                if (section == "git_cli" && subsection == "github") print "FILE_GH=false;"
                if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=false;"
            }
            /^[[:space:]]*enabled:[[:space:]]*auto/ {
                if (section == "git_cli" && subsection == "github") print "FILE_GH=auto;"
                if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=auto;"
            }
        ' "$SERVICES_CONFIG")

        if [[ -n "$config_settings" ]]; then
            eval "$config_settings"
        fi
    fi
}

# Load existing service configuration
load_existing_config() {
    if [[ -f "$SERVICES_CONFIG" ]]; then
        print_step "Loading existing service configuration..."

        parse_services_config

        # Only load if user didn't explicitly set the toggle
        if [[ "$CLAUDE_SET" == false && -n "$FILE_CLAUDE" ]]; then
            ENABLE_CLAUDE=$FILE_CLAUDE
        fi

        if [[ "$GEMINI_SET" == false && -n "$FILE_GEMINI" ]]; then
            ENABLE_GEMINI=$FILE_GEMINI
        fi

        if [[ "$CURSOR_SET" == false && -n "$FILE_CURSOR" ]]; then
            ENABLE_CURSOR=$FILE_CURSOR
        fi

        if [[ "$GH_SET" == false && -n "$FILE_GH" ]]; then
            ENABLE_GH=$FILE_GH
        fi

        if [[ "$GLAB_SET" == false && -n "$FILE_GLAB" ]]; then
            ENABLE_GLAB=$FILE_GLAB
        fi

        print_success "Loaded existing configuration"
    fi
}

# Write service configuration
write_services_config() {
    print_step "Writing service configuration..."

    mkdir -p "$(dirname "$SERVICES_CONFIG")"

    cat > "$SERVICES_CONFIG" << EOF
# Service Configuration
# Generated by bootstrap.sh on $(date)
#
# Controls which AI agents are enabled for parallel orchestration.
# Edit this file or run: ./bootstrap.sh --reconfigure [--enable|--disable]-<service>

services:
  # Claude Code CLI - Anthropic's AI assistant
  # Install: npm install -g @anthropic-ai/claude-code
  claude:
    enabled: $ENABLE_CLAUDE
    command: claude
    description: "Deep reasoning, security analysis, complex logic"
    model_tiers:
      - haiku    # Fast, economical
      - sonnet   # Balanced (default)
      - opus     # Maximum capability

  # Gemini CLI - Google's AI assistant
  # Install: npm install -g @google/gemini-cli
  gemini:
    enabled: $ENABLE_GEMINI
    command: gemini
    description: "Broad knowledge, creative solutions, research"
    model_tiers:
      - flash    # Fast (default)
      - pro      # Advanced

  # Cursor Agent - IDE-integrated AI
  # Install: Download from https://cursor.sh
  cursor:
    enabled: $ENABLE_CURSOR
    command: cursor
    description: "IDE-integrated context, code-specific analysis"
    model_tiers:
      - mini     # Lightweight
      - flash    # Balanced (default)
      - advanced # Maximum capability

  # Git CLI tools - Platform-specific Git hosting integrations
  git_cli:
    github:
      enabled: $ENABLE_GH
      command: gh
      description: "GitHub CLI for issue/PR management"
    gitlab:
      enabled: $ENABLE_GLAB
      command: glab
      description: "GitLab CLI for issue/MR management"
    detection:
      platform: auto  # auto | github | gitlab | git
      remote: origin  # overridable via MANIFEST_GIT_REMOTE

# Minimum agents required for parallel orchestration
# If fewer than this many services are enabled, parallel features are disabled
minimum_agents: 2

# Fallback behavior when enabled services are unavailable
fallback:
  strategy: continue_with_available  # Options: continue_with_available, abort, warn_user
  warn_threshold: 1  # Warn if only this many agents available
EOF

    print_success "Service configuration written to $SERVICES_CONFIG"
}

# Check platform and display info
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

# Check Claude authentication
# NOTE: We check credential files directly instead of running `claude auth status`
# because that command may spawn an interactive session that can hang
check_claude_auth() {
    if [[ "$ENABLE_CLAUDE" == false ]]; then
        return 0
    fi

    print_step "Checking Claude Code authentication..."

    if ! command_exists claude; then
        print_warning "Claude Code CLI not installed - skipping auth check"
        return 1
    fi

    # Check for auth token file (more reliable than `claude auth status` which may spawn interactive session)
    local claude_auth_files=(
        "$HOME/.config/claude-code/auth.json"
        "$HOME/.claude-code/auth.json"
        "$HOME/.config/@anthropic-ai/claude-code/auth.json"
    )

    for auth_file in "${claude_auth_files[@]}"; do
        if [[ -f "$auth_file" ]]; then
            print_success "Claude Code is authenticated"
            return 0
        fi
    done

    # Fallback: try non-interactive check with timeout
    if [[ -n "$TIMEOUT_CMD" ]]; then
        if $TIMEOUT_CMD 5 claude auth status &> /dev/null; then
            print_success "Claude Code is authenticated"
            return 0
        fi
    fi

    print_error "Claude Code is NOT authenticated"
    echo ""
    echo "  To authenticate, run one of the following after bootstrap completes:"
    echo ""
    echo "    # Browser-based OAuth (opens Anthropic Console):"
    echo -e "    ${CYAN}claude auth login${NC}"
    echo ""
    echo "    # Or set an API key directly:"
    echo -e "    ${CYAN}export ANTHROPIC_API_KEY='your-api-key'${NC}"
    echo ""
    echo "  Get an API key at: https://console.anthropic.com/settings/keys"
    echo ""
    return 1
}

# Setup Gemini authentication
setup_gemini_auth() {
    echo ""
    echo -e "${BOLD}Gemini Authentication Setup${NC}"
    echo "  1. Browser-based OAuth (recommended)"
    echo "  2. API Key (for headless/CI)"
    echo "  3. Skip"
    echo ""

    local auth_choice
    read -r -p "Choose option [1/2/3]: " auth_choice

    case $auth_choice in
        1)
            if command_exists gemini; then
                print_step "Running 'gemini auth login'..."
                gemini auth login
                return $?
            else
                print_error "Gemini CLI not found."
                return 1
            fi
            ;;
        2)
            echo ""
            echo "  Get an API key at: https://aistudio.google.com/apikey"
            echo -n "  Enter your Gemini API Key: "
            local api_key
            read -rs api_key
            echo "" # Newline after silent input

            if [[ -n "$api_key" ]]; then
                local env_file="$TARGET_DIR/gemini_env.sh"

                # Escape single quotes to prevent injection
                local safe_key="${api_key//\'/\'\\\'\'}"

                # Create file with restrictive permissions
                touch "$env_file"
                chmod 600 "$env_file"

                echo "export GEMINI_API_KEY='$safe_key'" > "$env_file"
                print_success "API key saved to $env_file (mode 600)"

                # Source it for current session
                export GEMINI_API_KEY="$api_key"
                return 0
            else
                print_warning "No API key entered."
                return 1
            fi
            ;;
        *)
            return 1
            ;;
    esac
}

# Check Gemini authentication
# NOTE: We check credential files directly instead of running `gemini auth status`
# because that command spawns a full agent session that can hang on tool execution
check_gemini_auth() {
    if [[ "$ENABLE_GEMINI" == false ]]; then
        return 0
    fi

    print_step "Checking Gemini CLI authentication..."

    if ! command_exists gemini; then
        print_warning "Gemini CLI not installed - skipping auth check"
        return 1
    fi

    # Check for API key in environment or config
    if [[ -n "$GOOGLE_API_KEY" ]] || [[ -n "$GEMINI_API_KEY" ]]; then
        print_success "Gemini CLI is authenticated (API key)"
        return 0
    fi

    # Check for OAuth credentials file (more reliable than `gemini auth status` which spawns an agent)
    if [[ -f "$HOME/.gemini/oauth_creds.json" ]]; then
        print_success "Gemini CLI is authenticated (OAuth)"
        return 0
    fi

    # Check for config file
    if [[ -f "$HOME/.gemini/config.json" ]] || [[ -f "$HOME/.config/gemini/credentials.json" ]]; then
        print_success "Gemini CLI is authenticated (credentials file)"
        return 0
    fi

    print_warning "Gemini CLI is NOT authenticated"

    if prompt_yes_no "Do you want to set up Gemini authentication now?"; then
        setup_gemini_auth
        return $?
    fi

    print_error "Gemini CLI remains unauthenticated"
    echo ""
    echo "  To authenticate, run one of the following after bootstrap completes:"
    echo ""
    echo "    # Browser-based OAuth (recommended for personal use):"
    echo -e "    ${CYAN}gemini auth login${NC}"
    echo ""
    echo "    # Or set an API key in your shell profile:"
    echo -e "    ${CYAN}export GEMINI_API_KEY='your-api-key'${NC}"
    echo ""
    echo "  Get an API key at: https://aistudio.google.com/apikey"
    echo ""
    return 1
}

# Check GitHub CLI authentication
check_gh_auth() {
    if [[ "$ENABLE_GH" == false ]]; then
        return 0
    fi

    print_step "Checking GitHub CLI authentication..."

    if ! command_exists gh; then
        print_warning "GitHub CLI not installed - skipping auth check"
        return 1
    fi

    if gh auth status &> /dev/null 2>&1; then
        print_success "GitHub CLI is authenticated"
        return 0
    fi

    print_error "GitHub CLI is NOT authenticated"
    echo ""
    echo "  To authenticate, run the following after bootstrap completes:"
    echo ""
    echo -e "    ${CYAN}gh auth login${NC}"
    echo ""
    return 1
}

# Check GitLab CLI authentication
check_glab_auth() {
    if [[ "$ENABLE_GLAB" == false ]]; then
        return 0
    fi

    print_step "Checking GitLab CLI authentication..."

    if ! command_exists glab; then
        print_warning "GitLab CLI not installed - skipping auth check"
        return 1
    fi

    if glab auth status &> /dev/null 2>&1; then
        print_success "GitLab CLI is authenticated"
        return 0
    fi

    print_error "GitLab CLI is NOT authenticated"
    echo ""
    echo "  To authenticate, run the following after bootstrap completes:"
    echo ""
    echo -e "    ${CYAN}glab auth login${NC}"
    echo ""
    return 1
}

# Deploy configuration files
deploy_configs() {
    print_header "Deploying Configuration Files"

    local source_dir="$SCRIPT_DIR/.claude"

    if [[ ! -d "$source_dir" ]]; then
        print_error "Source directory not found: $source_dir"
        exit 1
    fi

    # Check for existing installation
    if [[ -d "$TARGET_DIR" ]]; then
        if [[ "$FORCE" == true ]]; then
            print_warning "Overwriting existing installation (--force)"
        else
            echo ""
            print_warning "Existing installation found at $TARGET_DIR"
            echo ""
            echo "Options:"
            echo "  1. Backup and replace"
            echo "  2. Merge (keep existing, add new)"
            echo "  3. Cancel"
            echo ""
            read -r -p "Choose option [1/2/3]: " choice

            case $choice in
                1)
                    local backup_dir
                    backup_dir="$TARGET_DIR.backup.$(date +%Y%m%d_%H%M%S)"
                    print_step "Backing up to $backup_dir"
                    mv "$TARGET_DIR" "$backup_dir"
                    print_success "Backup created"
                    ;;
                2)
                    print_step "Merging configurations..."
                    # Merge mode - copy only new files
                    rsync -av --ignore-existing "$source_dir/" "$TARGET_DIR/"
                    print_success "Configurations merged"
                    # Still write services config
                    write_services_config
                    return 0
                    ;;
                3 | *)
                    print_info "Installation cancelled"
                    exit 0
                    ;;
            esac
        fi
    fi

    # Create target directory and copy files
    print_step "Creating $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
    chmod 700 "$TARGET_DIR"

    print_step "Copying configuration files..."
    cp -R "$source_dir"/* "$TARGET_DIR/"
    # Copy dot-prefixed directories (e.g. .plans/) that the glob above skips
    cp -R "$source_dir"/.[!.]* "$TARGET_DIR/" 2> /dev/null || true

    # Make scripts executable
    if [[ -d "$TARGET_DIR/scripts" ]]; then
        chmod +x "$TARGET_DIR/scripts"/*.sh 2> /dev/null || true
        print_success "Made scripts executable"
    fi

    # Create output directory
    mkdir -p "$TARGET_DIR/.agent_outputs"

    # Write services configuration
    write_services_config

    print_success "Configuration files deployed to $TARGET_DIR"

    # Deploy Cursor configuration
    deploy_cursor_configs

    # Deploy Gemini configuration
    deploy_gemini_configs

    # List deployed files
    echo ""
    print_info "Deployed files:"
    find "$TARGET_DIR" -type f \( -name "*.md" -o -name "*.yml" -o -name "*.sh" \) 2> /dev/null | head -20 | while read -r file; do
        echo "    ${file#"$HOME"/}"
    done
}

# Deploy Cursor IDE configuration (mirrors .claude with symlinks)
deploy_cursor_configs() {
    print_step "Deploying Cursor IDE configuration..."

    local cursor_source_dir="$SCRIPT_DIR/.cursor"

    if [[ ! -d "$cursor_source_dir" ]]; then
        print_warning "Cursor configuration source not found: $cursor_source_dir"
        print_info "Skipping Cursor config deployment"
        return 0
    fi

    # Create .cursor directory structure
    mkdir -p "$CURSOR_TARGET_DIR/rules"

    # Copy .mdc rule files
    if [[ -d "$cursor_source_dir/rules" ]]; then
        cp "$cursor_source_dir/rules"/*.mdc "$CURSOR_TARGET_DIR/rules/" 2> /dev/null || true
        print_success "Deployed Cursor rules to $CURSOR_TARGET_DIR/rules/"
    fi

    # Create symlinks for shared assets (pointing to ~/.claude/)
    local symlinks=(
        "scripts:$TARGET_DIR/scripts"
        "config:$TARGET_DIR/config"
        "prompts:$TARGET_DIR/prompts"
        ".plans:$TARGET_DIR/.plans"
    )

    for entry in "${symlinks[@]}"; do
        local name="${entry%%:*}"
        local target="${entry#*:}"
        local link_path="$CURSOR_TARGET_DIR/$name"

        if [[ -e "$target" ]]; then
            # Remove existing file/link/dir at the link path
            rm -rf "$link_path"
            ln -sf "$target" "$link_path"
            print_success "Symlinked $link_path -> $target"
        else
            print_warning "Symlink target not found: $target (skipping $name)"
        fi
    done

    print_success "Cursor configuration deployed to $CURSOR_TARGET_DIR"
}

# Deploy Gemini CLI configuration (mirrors .claude with symlinks)
deploy_gemini_configs() {
    print_step "Deploying Gemini CLI configuration..."

    local gemini_source_dir="$SCRIPT_DIR/.gemini"

    if [[ ! -d "$gemini_source_dir" ]]; then
        print_warning "Gemini configuration source not found: $gemini_source_dir"
        print_info "Skipping Gemini config deployment"
        return 0
    fi

    # Create .gemini directory structure
    mkdir -p "$GEMINI_TARGET_DIR/commands"
    mkdir -p "$GEMINI_TARGET_DIR/skills/code-quality"

    # Copy GEMINI.md
    if [[ -f "$gemini_source_dir/GEMINI.md" ]]; then
        cp "$gemini_source_dir/GEMINI.md" "$GEMINI_TARGET_DIR/GEMINI.md"
        print_success "Deployed GEMINI.md to $GEMINI_TARGET_DIR/"
    fi

    # Copy TOML command files
    if [[ -d "$gemini_source_dir/commands" ]]; then
        cp "$gemini_source_dir/commands"/*.toml "$GEMINI_TARGET_DIR/commands/" 2> /dev/null || true
        print_success "Deployed Gemini commands to $GEMINI_TARGET_DIR/commands/"
    fi

    # Copy settings.json (project settings, not auth)
    if [[ -f "$gemini_source_dir/settings.json" ]]; then
        # Merge with existing settings rather than overwriting (preserve auth)
        if [[ -f "$GEMINI_TARGET_DIR/settings.json" ]]; then
            print_info "Existing settings.json found - preserving (manual merge may be needed)"
        else
            cp "$gemini_source_dir/settings.json" "$GEMINI_TARGET_DIR/settings.json"
            print_success "Deployed settings.json to $GEMINI_TARGET_DIR/"
        fi
    fi

    # Create symlinks for shared assets (pointing to ~/.claude/)
    local symlinks=(
        "scripts:$TARGET_DIR/scripts"
        "config:$TARGET_DIR/config"
        "prompts:$TARGET_DIR/prompts"
        ".plans:$TARGET_DIR/.plans"
    )

    for entry in "${symlinks[@]}"; do
        local name="${entry%%:*}"
        local target="${entry#*:}"
        local link_path="$GEMINI_TARGET_DIR/$name"

        if [[ -e "$target" ]]; then
            # Remove existing file/link/dir at the link path
            rm -rf "$link_path"
            ln -sf "$target" "$link_path"
            print_success "Symlinked $link_path -> $target"
        else
            print_warning "Symlink target not found: $target (skipping $name)"
        fi
    done

    # Symlink the code-quality skill
    local skill_target="$TARGET_DIR/skills/code-quality/SKILL.md"
    local skill_link="$GEMINI_TARGET_DIR/skills/code-quality/SKILL.md"
    if [[ -f "$skill_target" ]]; then
        ln -sf "$skill_target" "$skill_link"
        print_success "Symlinked code-quality skill"
    fi

    print_success "Gemini configuration deployed to $GEMINI_TARGET_DIR"
}

# Verify installation
verify_installation() {
    print_header "Verifying Installation"

    local errors=0

    # Check deployed files
    print_step "Checking deployed files..."

    local required_files=(
        "$TARGET_DIR/CLAUDE.md"
        "$TARGET_DIR/scripts/parallel_agent.sh"
        "$TARGET_DIR/scripts/git_platform.sh"
        "$TARGET_DIR/scripts/git_ops.sh"
        "$TARGET_DIR/config/command_config.yml"
        "$TARGET_DIR/config/validation_criteria.yml"
        "$TARGET_DIR/config/services.yml"
        "$CURSOR_TARGET_DIR/rules/orchestration.mdc"
        "$GEMINI_TARGET_DIR/GEMINI.md"
        "$GEMINI_TARGET_DIR/commands/project-commit.toml"
    )

    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "Found: ${file#"$HOME"/}"
        else
            print_error "Missing: ${file#"$HOME"/}"
            errors=$((errors + 1))
        fi
    done

    # Check CLI tools based on enabled services
    echo ""
    print_step "Checking enabled CLI tools..."

    local available_tools=0
    local enabled_count=0

    if [[ "$ENABLE_CLAUDE" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists claude; then
            print_success "claude is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "claude is not available (enabled but not installed)"
        fi
    else
        print_info "claude is disabled"
    fi

    if [[ "$ENABLE_GEMINI" == true ]]; then
        enabled_count=$((enabled_count + 1))
        if command_exists gemini; then
            print_success "gemini is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "gemini is not available (enabled but not installed)"
        fi
    else
        print_info "gemini is disabled"
    fi

    if [[ "$ENABLE_CURSOR" == true ]]; then
        enabled_count=$((enabled_count + 1))
        local cursor_found=false
        if [[ "$PLATFORM" == "macos" ]]; then
            if [[ -d "/Applications/Cursor.app" ]] || command_exists cursor; then
                cursor_found=true
            fi
        else
            if command_exists cursor; then
                cursor_found=true
            fi
        fi

        if [[ "$cursor_found" == true ]]; then
            print_success "cursor is available (enabled)"
            available_tools=$((available_tools + 1))
        else
            print_warning "cursor is not available (enabled but not installed)"
        fi
    else
        print_info "cursor is disabled"
    fi

    # Check Git CLI tools
    if [[ "$ENABLE_GH" == true ]]; then
        if command_exists gh; then
            print_success "gh (GitHub CLI) is available"
        else
            print_warning "gh is enabled but not installed"
        fi
    else
        print_info "gh (GitHub CLI) is disabled"
    fi

    if [[ "$ENABLE_GLAB" == true ]]; then
        if command_exists glab; then
            print_success "glab (GitLab CLI) is available"
        else
            print_warning "glab is enabled but not installed"
        fi
    else
        print_info "glab (GitLab CLI) is disabled"
    fi

    # Check jq
    if command_exists jq; then
        print_success "jq is installed (required by git_ops.sh)"
    else
        print_warning "jq is not installed - git_ops.sh will have limited functionality"
    fi

    # Summary
    echo ""
    if [[ $errors -eq 0 ]]; then
        print_success "Installation verified successfully"
    else
        print_error "Installation has $errors error(s)"
    fi

    if [[ $enabled_count -lt 2 ]]; then
        print_warning "Only $enabled_count services enabled - parallel agent features require at least 2"
    elif [[ $available_tools -lt 2 ]]; then
        print_warning "Only $available_tools/$enabled_count enabled tools are installed - parallel features may be limited"
    fi

    return $errors
}

# Print final summary
print_summary() {
    print_header "Setup Complete"

    echo -e "${BOLD}Installation Summary:${NC}"
    echo ""
    echo "  Claude Config:  $TARGET_DIR"
    echo "  Cursor Config:  $CURSOR_TARGET_DIR"
    echo "  Gemini Config:  $GEMINI_TARGET_DIR"
    echo "  Agent Outputs:  $TARGET_DIR/.agent_outputs"
    echo "  Services Config: $TARGET_DIR/config/services.yml"
    echo ""

    echo -e "${BOLD}Service Status:${NC}"
    echo ""
    if [[ "$ENABLE_CLAUDE" == true ]]; then
        if command_exists claude; then
            echo -e "  ${GREEN}✓${NC} claude (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} claude (enabled, not installed)"
        fi
    else
        echo -e "  ${RED}✗${NC} claude (disabled)"
    fi

    if [[ "$ENABLE_GEMINI" == true ]]; then
        if command_exists gemini; then
            echo -e "  ${GREEN}✓${NC} gemini (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} gemini (enabled, not installed)"
        fi
    else
        echo -e "  ${RED}✗${NC} gemini (disabled)"
    fi

    if [[ "$ENABLE_CURSOR" == true ]]; then
        local cursor_found=false
        if [[ "$PLATFORM" == "macos" ]]; then
            if [[ -d "/Applications/Cursor.app" ]] || command_exists cursor; then
                cursor_found=true
            fi
        else
            if command_exists cursor; then
                cursor_found=true
            fi
        fi

        if [[ "$cursor_found" == true ]]; then
            echo -e "  ${GREEN}✓${NC} cursor (enabled, installed)"
        else
            echo -e "  ${YELLOW}○${NC} cursor (enabled, not installed)"
        fi
    else
        echo -e "  ${RED}✗${NC} cursor (disabled)"
    fi
    echo ""

    echo -e "${BOLD}Authentication Commands:${NC}"
    echo ""
    echo "  If any services above need authentication, run these commands:"
    echo ""
    if [[ "$ENABLE_CLAUDE" == true ]]; then
        echo -e "    Claude:  ${CYAN}claude auth login${NC}  or  ${CYAN}export ANTHROPIC_API_KEY='...'${NC}"
    fi
    if [[ "$ENABLE_GEMINI" == true ]]; then
        echo -e "    Gemini:  ${CYAN}gemini auth login${NC}  or  ${CYAN}export GEMINI_API_KEY='...'${NC}"
    fi
    if [[ "$ENABLE_GH" == true ]]; then
        echo -e "    GitHub:  ${CYAN}gh auth login${NC}"
    fi
    if [[ "$ENABLE_GLAB" == true ]]; then
        echo -e "    GitLab:  ${CYAN}glab auth login${NC}"
    fi
    if [[ "$ENABLE_CURSOR" == true ]]; then
        echo "    Cursor:  Sign in within the Cursor IDE"
    fi
    echo ""

    echo -e "${BOLD}Reconfigure Services:${NC}"
    echo ""
    echo "  # Enable/disable services"
    echo "  ./bootstrap.sh --reconfigure --disable-cursor"
    echo "  ./bootstrap.sh --reconfigure --enable-gemini --disable-claude"
    echo ""
    echo "  # Or edit directly:"
    echo "  \$EDITOR ~/.claude/config/services.yml"
    echo ""

    echo -e "${BOLD}Tip: Easy Access${NC}"
    echo ""
    echo "  Add an alias to run 'manifest' from anywhere:"
    echo ""
    if [[ "$SHELL" == *"zsh"* ]]; then
        echo -e "  ${CYAN}echo 'alias manifest=\"~/.claude/scripts/parallel_agent.sh\"' >> ~/.zshrc && source ~/.zshrc${NC}"
    elif [[ "$SHELL" == *"bash"* ]]; then
        echo -e "  ${CYAN}echo 'alias manifest=\"~/.claude/scripts/parallel_agent.sh\"' >> ~/.bashrc && source ~/.bashrc${NC}"
    else
        echo -e "  ${CYAN}alias manifest=\"~/.claude/scripts/parallel_agent.sh\"${NC}"
        echo "  (Add to your shell profile)"
    fi
    echo ""

    echo -e "${BOLD}Quick Start:${NC}"
    echo ""
    echo "  # Test parallel agents (uses enabled services only)"
    echo "  ~/.claude/scripts/parallel_agent.sh --json 'Hello from all agents'"
    echo ""
    echo "  # Code review with enabled agents"
    echo "  ~/.claude/scripts/parallel_agent.sh --json --review /path/to/file.py"
    echo ""
    echo "  # Use Claude Code commands"
    echo "  claude  # Start Claude Code CLI"
    echo "  # Then use: /refactor-python, /docs-readme, /docs-improve, etc."
    echo ""

    echo -e "${BOLD}Documentation:${NC}"
    echo ""
    echo "  Main guide:     ~/.claude/CLAUDE.md"
    echo "  Commands:       ~/.claude/commands/"
    echo "  Cursor rules:   ~/.cursor/rules/"
    echo "  Gemini commands: ~/.gemini/commands/"
    echo "  Config:         ~/.claude/config/"
    echo ""
}

# Reconfigure mode - only update services config
run_reconfigure() {
    print_header "Reconfiguring Services"

    # Load existing config first
    load_existing_config

    # Show current vs new configuration
    echo -e "${BOLD}Service Configuration Changes:${NC}"
    echo ""

    if [[ -f "$SERVICES_CONFIG" ]]; then
        # Use values parsed by load_existing_config -> parse_services_config
        local old_claude=${FILE_CLAUDE:-unknown}
        local old_gemini=${FILE_GEMINI:-unknown}
        local old_cursor=${FILE_CURSOR:-unknown}

        echo "  Claude:  $old_claude → $ENABLE_CLAUDE"
        echo "  Gemini:  $old_gemini → $ENABLE_GEMINI"
        echo "  Cursor:  $old_cursor → $ENABLE_CURSOR"
    else
        echo "  Claude:  (new) → $ENABLE_CLAUDE"
        echo "  Gemini:  (new) → $ENABLE_GEMINI"
        echo "  Cursor:  (new) → $ENABLE_CURSOR"
    fi
    echo ""

    if prompt_yes_no "Apply these changes?"; then
        write_services_config
        print_success "Services reconfigured"
        echo ""
        print_info "The parallel_agent.sh script will use these settings on next run"
    else
        print_info "Reconfiguration cancelled"
    fi
}

# Main execution
main() {
    # Handle reconfigure mode separately
    if [[ "$RECONFIGURE" == true ]]; then
        run_reconfigure
        exit 0
    fi

    print_header "AI Agent Support Framework Bootstrap"

    echo "This script will:"
    echo "  1. Install required CLI tools (based on enabled services)"
    echo "  2. Deploy configuration files to ~/.claude"
    echo "  3. Check authentication status for each enabled service"
    echo ""

    echo -e "${BOLD}Services to configure:${NC}"
    echo "  Claude CLI:  $(if [[ "$ENABLE_CLAUDE" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Gemini CLI:  $(if [[ "$ENABLE_GEMINI" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Cursor:      $(if [[ "$ENABLE_CURSOR" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo ""

    if ! prompt_yes_no "Continue with setup?"; then
        print_info "Setup cancelled"
        exit 0
    fi

    # Check platform
    check_platform

    # Load existing config if present (for defaults)
    load_existing_config

    # Install dependencies
    if [[ "$SKIP_INSTALL" == false ]]; then
        print_header "Installing Dependencies"

        install_package_manager
        install_node
        install_claude
        install_gemini
        install_github_cli
        install_gitlab_cli
        check_jq
        check_cursor
    else
        print_info "Skipping installation (--skip-install)"
    fi

    # Deploy configurations
    deploy_configs

    # Check authentication status
    if [[ "$SKIP_AUTH" == false ]]; then
        print_header "Checking Authentication Status"

        local auth_failures=0

        # Claude auth check
        if [[ "$ENABLE_CLAUDE" == true ]]; then
            check_claude_auth || auth_failures=$((auth_failures + 1))
        fi

        # Gemini auth check
        if [[ "$ENABLE_GEMINI" == true ]]; then
            check_gemini_auth || auth_failures=$((auth_failures + 1))
        fi

        # GitHub CLI auth check
        if [[ "$ENABLE_GH" == true ]]; then
            check_gh_auth || auth_failures=$((auth_failures + 1))
        fi

        # GitLab CLI auth check
        if [[ "$ENABLE_GLAB" == true ]]; then
            check_glab_auth || auth_failures=$((auth_failures + 1))
        fi

        # Cursor auth info
        if [[ "$ENABLE_CURSOR" == true ]]; then
            local cursor_found=false
            if [[ "$PLATFORM" == "macos" ]]; then
                if [[ -d "/Applications/Cursor.app" ]] || command_exists cursor; then
                    cursor_found=true
                fi
            else
                if command_exists cursor; then
                    cursor_found=true
                fi
            fi

            if [[ "$cursor_found" == true ]]; then
                print_step "Checking Cursor authentication..."
                print_info "Cursor authentication is handled within the Cursor IDE"
                print_info "Open Cursor and sign in to enable the cursor agent"
            fi
        fi

        # Summary of auth failures
        if [[ $auth_failures -gt 0 ]]; then
            echo ""
            print_warning "$auth_failures service(s) require authentication (see instructions above)"
        else
            echo ""
            print_success "All enabled services are authenticated"
        fi
    else
        print_info "Skipping authentication checks (--skip-auth)"
    fi

    # Verify installation
    verify_installation

    # Print summary
    print_summary
}

# Run main
main "$@"
