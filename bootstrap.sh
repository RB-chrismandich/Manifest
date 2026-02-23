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
#   --enable-codex      Enable Codex CLI (default: enabled)
#   --disable-codex     Disable Codex CLI
#   --enable-gh         Enable GitHub CLI (default: auto-detect)
#   --disable-gh        Disable GitHub CLI
#   --enable-glab       Enable GitLab CLI (default: auto-detect)
#   --disable-glab      Disable GitLab CLI
#
# Other options:
#   --skip-install      Skip CLI tool installation
#   --skip-auth         Skip authentication checks
#   --install-mcp       Configure default MCP servers for enabled agents
#   --force             Overwrite existing ~/.claude without prompting
#   --reconfigure       Only update service toggles (skip full setup)

set -e

# Ensure cursor is restored on exit
trap 'tput cnorm 2>/dev/null' EXIT

# Colors for output (used in sourced libs via echo -e)
# shellcheck disable=SC2034
RED='\033[0;31m'
# shellcheck disable=SC2034
GREEN='\033[0;32m'
# shellcheck disable=SC2034
BLUE='\033[0;34m'
# shellcheck disable=SC2034
YELLOW='\033[1;33m'
# shellcheck disable=SC2034
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_LIB_DIR="$SCRIPT_DIR/bootstrap/lib"
BOOTSTRAP_MODULE_DIR="${BOOTSTRAP_MODULE_DIR:-$SCRIPT_DIR/bootstrap/modules}"
TARGET_DIR="$HOME/.claude"
# shellcheck disable=SC2034
CURSOR_TARGET_DIR="$HOME/.cursor"
# shellcheck disable=SC2034
GEMINI_TARGET_DIR="$HOME/.gemini"
# shellcheck disable=SC2034
CODEX_TARGET_DIR="$HOME/.codex"
MANIFEST_STATE_DIR="$HOME/.manifest"
# shellcheck disable=SC2034
MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/orchestration/outputs"
# shellcheck disable=SC2034
MANIFEST_TMP_DIR="$MANIFEST_STATE_DIR/tmp"
SERVICES_CONFIG="$TARGET_DIR/config/services.yml"

# Detect platform/runtime defaults (initialized by initialize_platform_runtime)
PLATFORM="unknown"
export DISTRO=""
# shellcheck disable=SC2034
PKG_MANAGER=""
# shellcheck disable=SC2034
TIMEOUT_CMD=""

# Script name for help output
# shellcheck disable=SC2034
BOOTSTRAP_SCRIPT_NAME="$0"

load_bootstrap_libs() {
    local libs=(
        "common.sh"
        "modules.sh"
        "platform.sh"
        "config.sh"
        "install.sh"
        "auth.sh"
        "deploy.sh"
        "mcp.sh"
    )
    local lib
    for lib in "${libs[@]}"; do
        if [[ ! -f "$BOOTSTRAP_LIB_DIR/$lib" ]]; then
            echo -e "${RED}Missing required bootstrap library: $BOOTSTRAP_LIB_DIR/$lib${NC}"
            exit 1
        fi
        # shellcheck disable=SC1090
        source "$BOOTSTRAP_LIB_DIR/$lib"
    done
}

load_bootstrap_libs
set_bootstrap_defaults
parse_bootstrap_args "$@"
initialize_platform_runtime

# Bootstrap core routines are sourced from bootstrap/lib/*.sh
# Reconfigure mode - only update services config
run_reconfigure() {
    print_header "Reconfiguring Services"

    # Load existing config first
    load_existing_config
    run_bootstrap_hook "after_config_load"

    # Show current vs new configuration
    echo -e "${BOLD}Service Configuration Changes:${NC}"
    echo ""

    if [[ -f "$SERVICES_CONFIG" ]]; then
        # Use values parsed by load_existing_config -> parse_services_config
        local old_claude=${FILE_CLAUDE:-unknown}
        local old_gemini=${FILE_GEMINI:-unknown}
        local old_cursor=${FILE_CURSOR:-unknown}
        local old_codex=${FILE_CODEX:-unknown}

        echo "  Claude:  $old_claude → $ENABLE_CLAUDE"
        echo "  Gemini:  $old_gemini → $ENABLE_GEMINI"
        echo "  Cursor:  $old_cursor → $ENABLE_CURSOR"
        echo "  Codex:   $old_codex → $ENABLE_CODEX"
    else
        echo "  Claude:  (new) → $ENABLE_CLAUDE"
        echo "  Gemini:  (new) → $ENABLE_GEMINI"
        echo "  Cursor:  (new) → $ENABLE_CURSOR"
        echo "  Codex:   (new) → $ENABLE_CODEX"
    fi
    echo ""

    if prompt_yes_no "Apply these changes?"; then
        setup_manifest_state_dirs
        configure_shell_profile_state
        write_services_config
        if [[ "$INSTALL_MCP" == true ]]; then
            install_mcp_servers
        fi
        run_bootstrap_hook "after_deploy"

        # Install/update Python dependencies
        print_header "Updating Python Dependencies"
        install_python_dependencies

        print_success "Services reconfigured"
        echo ""
        print_info "The parallel_agent.sh script will use these settings on next run"
    else
        print_info "Reconfiguration cancelled"
    fi
}

# Main execution
main() {
    load_bootstrap_modules

    # Handle reconfigure mode separately
    if [[ "$RECONFIGURE" == true ]]; then
        run_reconfigure
        exit 0
    fi

    print_header "AI Agent Support Framework Bootstrap"

    echo "This script will:"
    echo "  1. Install required CLI tools (based on enabled services)"
    echo "  2. Deploy configuration files with ~/.claude as primary"
    echo "  3. Check authentication status for each enabled service"
    echo "  4. Configure MCP servers if --install-mcp is set"
    echo ""

    echo -e "${BOLD}Services to configure:${NC}"
    echo "  Claude CLI:  $(if [[ "$ENABLE_CLAUDE" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Gemini CLI:  $(if [[ "$ENABLE_GEMINI" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Cursor:      $(if [[ "$ENABLE_CURSOR" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Codex CLI:   $(if [[ "$ENABLE_CODEX" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo ""

    if ! prompt_yes_no "Continue with setup?"; then
        print_info "Setup cancelled"
        exit 0
    fi

    # Check platform
    check_platform

    # Load existing config if present (for defaults)
    load_existing_config
    run_bootstrap_hook "after_config_load"

    # Prepare shared state root used by orchestration runtime.
    setup_manifest_state_dirs
    configure_shell_profile_state

    # Install dependencies
    if [[ "$SKIP_INSTALL" == false ]]; then
        print_header "Installing Dependencies"
        run_bootstrap_hook "before_install"

        install_package_manager
        install_node
        install_claude
        install_gemini
        install_codex
        install_github_cli
        install_gitlab_cli
        check_jq
        check_cursor
    else
        print_info "Skipping installation (--skip-install)"
    fi

    # Deploy configurations
    deploy_configs
    run_bootstrap_hook "after_deploy"

    # Install Python dependencies for parallel_agent.py
    install_python_dependencies

    # Configure default MCP servers when requested
    if [[ "$INSTALL_MCP" == true ]]; then
        install_mcp_servers
    fi

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

        # Codex auth check
        if [[ "$ENABLE_CODEX" == true ]]; then
            check_codex_auth || auth_failures=$((auth_failures + 1))
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
        run_bootstrap_hook "after_auth"
    else
        print_info "Skipping authentication checks (--skip-auth)"
        run_bootstrap_hook "after_auth"
    fi

    # Verify installation
    verify_installation
    run_bootstrap_hook "after_verify"

    # Print summary
    print_summary
}

# Run main
main "$@"
