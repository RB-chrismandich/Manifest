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
#
# Other options:
#   --skip-install      Skip CLI tool installation
#   --skip-auth         Skip authentication setup
#   --force             Overwrite existing ~/.claude without prompting
#   --reconfigure       Only update service toggles (skip full setup)

set -e

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
SERVICES_CONFIG="$TARGET_DIR/config/services.yml"

# Detect platform
PLATFORM="unknown"
DISTRO=""
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

# Flags
SKIP_INSTALL=false
SKIP_AUTH=false
FORCE=false
RECONFIGURE=false

# Service toggles (default: all enabled)
ENABLE_CLAUDE=true
ENABLE_GEMINI=true
ENABLE_CURSOR=true

# Track if user explicitly set toggles
CLAUDE_SET=false
GEMINI_SET=false
CURSOR_SET=false

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
        -h|--help)
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
            echo ""
            echo "Other Options:"
            echo "  --skip-install      Skip CLI tool installation"
            echo "  --skip-auth         Skip authentication setup"
            echo "  --force             Overwrite existing ~/.claude without prompting"
            echo "  --reconfigure       Only update service toggles (skip full setup)"
            echo ""
            echo "Examples:"
            echo "  $0                              # Full setup with all services"
            echo "  $0 --disable-cursor             # Setup without Cursor"
            echo "  $0 --reconfigure --disable-gemini  # Just disable Gemini"
            echo "  $0 --skip-auth                  # Setup without authentication prompts"
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
    local prompt="$1"
    local default="${2:-y}"
    local response

    if [[ "$default" == "y" ]]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi

    read -r -p "$prompt" response
    response="${response:-$default}"

    [[ "$response" =~ ^[Yy]$ ]]
}

command_exists() {
    command -v "$1" &> /dev/null
}

# Load existing service configuration
load_existing_config() {
    if [[ -f "$SERVICES_CONFIG" ]]; then
        print_step "Loading existing service configuration..."

        # Only load if user didn't explicitly set the toggle
        if [[ "$CLAUDE_SET" == false ]]; then
            local claude_enabled=$(grep -E "^\s*claude:" "$SERVICES_CONFIG" | grep -oE "(true|false)" | head -1)
            [[ "$claude_enabled" == "true" ]] && ENABLE_CLAUDE=true || ENABLE_CLAUDE=false
        fi

        if [[ "$GEMINI_SET" == false ]]; then
            local gemini_enabled=$(grep -E "^\s*gemini:" "$SERVICES_CONFIG" | grep -oE "(true|false)" | head -1)
            [[ "$gemini_enabled" == "true" ]] && ENABLE_GEMINI=true || ENABLE_GEMINI=false
        fi

        if [[ "$CURSOR_SET" == false ]]; then
            local cursor_enabled=$(grep -E "^\s*cursor:" "$SERVICES_CONFIG" | grep -oE "(true|false)" | head -1)
            [[ "$cursor_enabled" == "true" ]] && ENABLE_CURSOR=true || ENABLE_CURSOR=false
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
                dnf|yum)
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
        local node_version=$(node --version)
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
        claude --version 2>/dev/null || true
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
check_claude_auth() {
    if [[ "$ENABLE_CLAUDE" == false ]]; then
        return 0
    fi

    print_step "Checking Claude Code authentication..."

    if ! command_exists claude; then
        print_warning "Claude Code CLI not installed - skipping auth check"
        return 1
    fi

    # Try to check auth status
    if claude auth status &>/dev/null; then
        print_success "Claude Code is authenticated"
        return 0
    else
        print_warning "Claude Code is not authenticated"
        return 1
    fi
}

# Setup Claude authentication
setup_claude_auth() {
    if [[ "$ENABLE_CLAUDE" == false ]]; then
        return 0
    fi

    if ! command_exists claude; then
        return 1
    fi

    echo ""
    echo -e "${BOLD}Claude Code Authentication Setup${NC}"
    echo ""
    echo "You will be redirected to authenticate with your Anthropic account."
    echo "This requires an active Claude subscription or API access."
    echo ""

    if prompt_yes_no "Start Claude Code authentication?"; then
        print_step "Starting authentication..."
        claude auth login

        if check_claude_auth; then
            print_success "Claude Code authentication successful"
            return 0
        else
            print_error "Claude Code authentication failed"
            return 1
        fi
    else
        print_warning "Skipping Claude Code authentication"
        return 1
    fi
}

# Check Gemini authentication
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
        print_success "Gemini API key found in environment"
        return 0
    fi

    # Try a simple auth check
    if gemini auth status &>/dev/null 2>&1; then
        print_success "Gemini CLI is authenticated"
        return 0
    fi

    # Check for config file
    if [[ -f "$HOME/.gemini/config.json" ]] || [[ -f "$HOME/.config/gemini/credentials.json" ]]; then
        print_success "Gemini credentials file found"
        return 0
    fi

    print_warning "Gemini CLI may not be authenticated"
    return 1
}

# Setup Gemini authentication
setup_gemini_auth() {
    if [[ "$ENABLE_GEMINI" == false ]]; then
        return 0
    fi

    if ! command_exists gemini; then
        return 1
    fi

    echo ""
    echo -e "${BOLD}Gemini CLI Authentication Setup${NC}"
    echo ""
    echo "Options for authentication:"
    echo "  1. OAuth login (recommended for personal use)"
    echo "  2. API key (for programmatic access)"
    echo ""
    echo "Get an API key at: https://aistudio.google.com/apikey"
    echo ""

    if prompt_yes_no "Start Gemini CLI authentication via OAuth?"; then
        print_step "Starting OAuth authentication..."
        gemini auth login

        if check_gemini_auth; then
            print_success "Gemini CLI authentication successful"
            return 0
        else
            print_warning "OAuth authentication may have failed"
        fi
    fi

    # Offer API key setup as alternative
    echo ""
    if prompt_yes_no "Set up Gemini API key instead?"; then
        echo ""
        read -r -p "Enter your Gemini API key: " api_key

        if [[ -n "$api_key" ]]; then
            # Add to shell profile
            local shell_profile=""
            if [[ -f "$HOME/.zshrc" ]]; then
                shell_profile="$HOME/.zshrc"
            elif [[ -f "$HOME/.bash_profile" ]]; then
                shell_profile="$HOME/.bash_profile"
            elif [[ -f "$HOME/.bashrc" ]]; then
                shell_profile="$HOME/.bashrc"
            fi

            if [[ -n "$shell_profile" ]]; then
                echo "" >> "$shell_profile"
                echo "# Gemini API Key (added by ai-agent-support-frameworks bootstrap)" >> "$shell_profile"
                echo "export GEMINI_API_KEY=\"$api_key\"" >> "$shell_profile"
                export GEMINI_API_KEY="$api_key"
                print_success "API key added to $shell_profile"
                print_info "Run 'source $shell_profile' or restart your terminal"
                return 0
            else
                print_warning "Could not find shell profile to add API key"
                echo "Add this to your shell profile:"
                echo "  export GEMINI_API_KEY=\"$api_key\""
            fi
        fi
    fi

    print_warning "Skipping Gemini authentication"
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
                    local backup_dir="$TARGET_DIR.backup.$(date +%Y%m%d_%H%M%S)"
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
                3|*)
                    print_info "Installation cancelled"
                    exit 0
                    ;;
            esac
        fi
    fi

    # Create target directory and copy files
    print_step "Creating $TARGET_DIR"
    mkdir -p "$TARGET_DIR"

    print_step "Copying configuration files..."
    cp -R "$source_dir"/* "$TARGET_DIR/"

    # Make scripts executable
    if [[ -d "$TARGET_DIR/scripts" ]]; then
        chmod +x "$TARGET_DIR/scripts"/*.sh 2>/dev/null || true
        print_success "Made scripts executable"
    fi

    # Create output directory
    mkdir -p "$TARGET_DIR/.agent_outputs"

    # Write services configuration
    write_services_config

    print_success "Configuration files deployed to $TARGET_DIR"

    # List deployed files
    echo ""
    print_info "Deployed files:"
    find "$TARGET_DIR" -type f \( -name "*.md" -o -name "*.yml" -o -name "*.sh" \) 2>/dev/null | head -20 | while read -r file; do
        echo "    ${file#$HOME/}"
    done
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
        "$TARGET_DIR/config/command_config.yml"
        "$TARGET_DIR/config/validation_criteria.yml"
        "$TARGET_DIR/config/services.yml"
    )

    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "Found: ${file#$HOME/}"
        else
            print_error "Missing: ${file#$HOME/}"
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
    echo "  Configuration: $TARGET_DIR"
    echo "  Agent Outputs: $TARGET_DIR/.agent_outputs"
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
    echo "  # Then use: /refactor, /improve-readme, /improve-docs, etc."
    echo ""

    echo -e "${BOLD}Documentation:${NC}"
    echo ""
    echo "  Main guide: ~/.claude/CLAUDE.md"
    echo "  Commands:   ~/.claude/commands/"
    echo "  Config:     ~/.claude/config/"
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
        local old_claude=$(grep -E "^\s*claude:" "$SERVICES_CONFIG" | grep -oE "(true|false)" | head -1)
        local old_gemini=$(grep -E "^\s*gemini:" "$SERVICES_CONFIG" | grep -oE "(true|false)" | head -1)
        local old_cursor=$(grep -E "^\s*cursor:" "$SERVICES_CONFIG" | grep -oE "(true|false)" | head -1)

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
    echo "  3. Set up authentication for each enabled service"
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
        check_cursor
    else
        print_info "Skipping installation (--skip-install)"
    fi

    # Deploy configurations
    deploy_configs

    # Setup authentication
    if [[ "$SKIP_AUTH" == false ]]; then
        print_header "Setting Up Authentication"

        # Claude auth
        if [[ "$ENABLE_CLAUDE" == true ]]; then
            if ! check_claude_auth; then
                setup_claude_auth
            fi
        fi

        # Gemini auth
        if [[ "$ENABLE_GEMINI" == true ]]; then
            if ! check_gemini_auth; then
                setup_gemini_auth
            fi
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
                echo ""
                print_info "Cursor authentication is handled within the Cursor IDE"
                print_info "Open Cursor and sign in to enable the cursor agent"
            fi
        fi
    else
        print_info "Skipping authentication setup (--skip-auth)"
    fi

    # Verify installation
    verify_installation

    # Print summary
    print_summary
}

# Run main
main "$@"
