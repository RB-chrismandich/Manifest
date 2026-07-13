#!/bin/bash
# Bootstrap script for AI Agent Support Framework
# Installs dependencies, deploys configurations, and sets up authentication
# Supports: macOS (Intel/Apple Silicon) and Linux (Debian/Ubuntu, RHEL/Fedora, Arch)
#
# Usage: ./bootstrap.sh [options]
#
# Service toggles:
#   --enable-claude       Enable Claude CLI (default: enabled)
#   --disable-claude      Disable Claude CLI
#   --enable-gemini       Enable Gemini CLI (default: enabled)
#   --disable-gemini      Disable Gemini CLI
#   --enable-cursor       Enable Cursor agent (default: enabled)
#   --disable-cursor      Disable Cursor agent
#   --enable-codex        Enable Codex CLI (default: enabled)
#   --disable-codex       Disable Codex CLI
#   --enable-antigravity  Enable Antigravity IDE (default: enabled)
#   --disable-antigravity Disable Antigravity IDE
#   --enable-graphify     Enable Graphify knowledge-graph CLI (default: enabled)
#   --disable-graphify    Disable Graphify knowledge-graph CLI
#   --enable-skillclaw    Enable SkillClaw session capture (default: disabled)
#   --disable-skillclaw   Disable SkillClaw session capture
#   --enable-browser-use  Enable browser-use for smoke-manage UI steps (default: disabled)
#   --disable-browser-use Disable browser-use
#   --enable-gh           Enable GitHub CLI (default: auto-detect)
#   --disable-gh          Disable GitHub CLI
#   --enable-glab         Enable GitLab CLI (default: auto-detect)
#   --disable-glab        Disable GitLab CLI
#
# Other options:
#   --skip-install      Skip CLI tool installation
#   --skip-auth         Skip authentication checks
#   --install-mcp       Configure default MCP servers for enabled agents
#   --force             Overwrite existing ~/.claude without prompting
#   --reconfigure       Update service toggles and refresh Python/browser-use
#                       dependencies (skips install and config deployment)

set -e

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
# shellcheck disable=SC2034
ANTIGRAVITY_TARGET_DIR="$HOME/.antigravity"
MANIFEST_STATE_DIR="$HOME/.manifest"
# shellcheck disable=SC2034
MANIFEST_OUTPUT_DIR="$MANIFEST_STATE_DIR/orchestration/outputs"
# shellcheck disable=SC2034
MANIFEST_TMP_DIR="$MANIFEST_STATE_DIR/tmp"
SERVICES_CONFIG="$TARGET_DIR/config/services.yml"

# Detect platform/runtime defaults (initialized by initialize_platform_runtime)
# shellcheck disable=SC2034  # consumed by sourced bootstrap/lib/*.sh
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
        "skillclaw.sh"
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
        local old_antigravity=${FILE_ANTIGRAVITY:-unknown}
        local old_graphify=${FILE_GRAPHIFY:-unknown}
        local old_skillclaw=${FILE_SKILLCLAW:-unknown}
        local old_browser_use=${FILE_BROWSER_USE:-unknown}

        echo "  Claude:      $old_claude → $ENABLE_CLAUDE"
        echo "  Gemini:      $old_gemini → $ENABLE_GEMINI"
        echo "  Cursor:      $old_cursor → $ENABLE_CURSOR"
        echo "  Codex:       $old_codex → $ENABLE_CODEX"
        echo "  Antigravity: $old_antigravity → $ENABLE_ANTIGRAVITY"
        echo "  Graphify:    $old_graphify → $ENABLE_GRAPHIFY"
        echo "  SkillClaw:   $old_skillclaw → $ENABLE_SKILLCLAW"
        echo "  browser-use: $old_browser_use → $ENABLE_BROWSER_USE"
    else
        echo "  Claude:      (new) → $ENABLE_CLAUDE"
        echo "  Gemini:      (new) → $ENABLE_GEMINI"
        echo "  Cursor:      (new) → $ENABLE_CURSOR"
        echo "  Codex:       (new) → $ENABLE_CODEX"
        echo "  Antigravity: (new) → $ENABLE_ANTIGRAVITY"
        echo "  Graphify:    (new) → $ENABLE_GRAPHIFY"
        echo "  SkillClaw:   (new) → $ENABLE_SKILLCLAW"
        echo "  browser-use: (new) → $ENABLE_BROWSER_USE"
    fi
    echo ""

    if prompt_yes_no "Apply these changes?"; then
        setup_manifest_state_dirs
        configure_shell_profile_state
        write_services_config
        skillclaw_apply_state
        if [[ "$INSTALL_MCP" == true ]]; then
            install_mcp_servers
        fi
        run_bootstrap_hook "after_deploy"

        # Install/update Python dependencies
        print_header "Updating Python Dependencies"
        install_python_dependencies
        install_browser_use
        install_smoke_deps
        install_graphify

        # Gate the deployed /graphify skill to match the new toggle — the gate
        # otherwise only runs inside deploy_configs, so a reconfigure-time
        # --disable-graphify would leave the skill deployed (issue #459).
        if [[ -d "$TARGET_DIR/skills" ]]; then
            gate_graphify_skill "$TARGET_DIR/skills"
        fi

        # Flag any disabled service whose deployed config is still present
        # (#549). warn_stale_disabled_configs is otherwise only called from
        # print_summary, which main() never reaches in --reconfigure mode —
        # so a disable-via-reconfigure (README's own documented workflow:
        # `--reconfigure --enable-gemini --disable-claude`) would never warn.
        warn_stale_disabled_configs

        print_success "Services reconfigured"
        echo ""
        print_info "The parallel_agent.py script will use these settings on next run"
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

    # Load existing config BEFORE showing the services banner, so the
    # displayed toggles match what will actually be deployed (explicit CLI
    # flags still win via the *_SET guards in load_existing_config).
    load_existing_config
    run_bootstrap_hook "after_config_load"
    echo ""

    echo -e "${BOLD}Services to configure:${NC}"
    echo "  Claude CLI:  $(if [[ "$ENABLE_CLAUDE" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Gemini CLI:  $(if [[ "$ENABLE_GEMINI" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Cursor:      $(if [[ "$ENABLE_CURSOR" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Codex CLI:   $(if [[ "$ENABLE_CODEX" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Antigravity: $(if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  Graphify:    $(if [[ "$ENABLE_GRAPHIFY" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  SkillClaw:   $(if [[ "$ENABLE_SKILLCLAW" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo "  browser-use: $(if [[ "$ENABLE_BROWSER_USE" == true ]]; then echo "enabled"; else echo "disabled"; fi)"
    echo ""

    if ! prompt_yes_no "Continue with setup?"; then
        print_info "Setup cancelled"
        exit 0
    fi

    # Check platform
    check_platform

    # Prepare shared state root used by orchestration runtime.
    setup_manifest_state_dirs
    configure_shell_profile_state

    # Install dependencies
    if [[ "$SKIP_INSTALL" == false ]]; then
        print_header "Installing Dependencies"
        run_bootstrap_hook "before_install"

        install_package_manager
        install_node
        # Per-tool installs return 1 as a soft signal (e.g. npm/brew missing);
        # under set -e an unguarded call aborted the whole bootstrap mid-flight
        # instead of continuing with the remaining tools (issue #318).
        local install_failures=0
        install_claude || install_failures=$((install_failures + 1))
        install_gemini || install_failures=$((install_failures + 1))
        install_codex || install_failures=$((install_failures + 1))
        install_github_cli || install_failures=$((install_failures + 1))
        install_gitlab_cli || install_failures=$((install_failures + 1))
        check_jq || install_failures=$((install_failures + 1))
        check_rsync || install_failures=$((install_failures + 1))
        check_cursor || install_failures=$((install_failures + 1))
        if [[ $install_failures -gt 0 ]]; then
            print_warning "$install_failures install step(s) failed — continuing with remaining setup"
        fi
    else
        print_info "Skipping installation (--skip-install)"
    fi

    # Deploy configurations
    deploy_configs
    run_bootstrap_hook "after_deploy"
    skillclaw_apply_state

    # Report-only orphan review of the just-deployed environment (fail-open; never deletes)
    reconcile_deploy_report || print_warning "reconcile review skipped (non-fatal)"

    # Install Python dependencies for parallel_agent.py
    install_python_dependencies
    install_browser_use
    install_smoke_deps
    install_graphify

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

        # Antigravity (agy) auth check
        if [[ "$ENABLE_ANTIGRAVITY" == true ]]; then
            check_antigravity_auth || auth_failures=$((auth_failures + 1))
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
            if command_exists cursor-agent || [[ -f "$HOME/.local/bin/cursor-agent" ]]; then
                print_step "Checking cursor-agent authentication..."
                print_info "Authenticate with: cursor-agent login  (or set CURSOR_API_KEY)"
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

    # Verify installation. It returns its error count, so an unguarded call
    # under set -e killed the script before the after_verify hook and the
    # summary's auth/quick-start guidance could run (issue #318).
    local verify_errors=0
    verify_installation || verify_errors=$?
    run_bootstrap_hook "after_verify"

    # Print summary
    print_summary

    if [[ $verify_errors -gt 0 ]]; then
        print_warning "Verification reported $verify_errors error(s) — see above"
        exit 1
    fi
}

# Run main
main "$@"
