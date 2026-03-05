#!/bin/bash

# Authentication and state helpers for bootstrap.sh. This file is sourced, not executed.

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

                # Create file with restrictive permissions securely
                write_file_securely "$env_file" "export GEMINI_API_KEY='$safe_key'
"

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

# Check Codex authentication
check_codex_auth() {
    if [[ "$ENABLE_CODEX" == false ]]; then
        return 0
    fi

    print_step "Checking Codex CLI authentication..."

    if ! command_exists codex; then
        print_warning "Codex CLI not installed - skipping auth check"
        return 1
    fi

    # Check for API key in environment first
    if [[ -n "$OPENAI_API_KEY" ]]; then
        print_success "Codex CLI is authenticated (API key)"
        return 0
    fi

    # Check for persisted auth files
    local codex_auth_files=(
        "$HOME/.codex/auth.json"
        "$HOME/.config/codex/auth.json"
    )

    for auth_file in "${codex_auth_files[@]}"; do
        if [[ -f "$auth_file" ]]; then
            print_success "Codex CLI is authenticated (credentials file)"
            return 0
        fi
    done

    print_error "Codex CLI is NOT authenticated"
    echo ""
    echo "  To authenticate, run one of the following after bootstrap completes:"
    echo ""
    echo "    # Browser-based login:"
    echo -e "    ${CYAN}codex auth login${NC}"
    echo ""
    echo "    # Or set an API key in your shell profile:"
    echo -e "    ${CYAN}export OPENAI_API_KEY='your-api-key'${NC}"
    echo ""
    echo "  Get an API key at: https://platform.openai.com/api-keys"
    echo ""
    return 1
}

# Configure shell profile defaults for Manifest runtime state.
# Adds export only once and preserves user overrides by using parameter expansion.
configure_shell_profile_state() {
    print_step "Configuring shell profile for Manifest state..."

    local profile_file=""
    case "$SHELL" in
        *zsh)
            profile_file="$HOME/.zshrc"
            ;;
        *bash)
            if [[ "$PLATFORM" == "macos" ]]; then
                profile_file="$HOME/.bash_profile"
            else
                profile_file="$HOME/.bashrc"
            fi
            ;;
        *)
            profile_file="$HOME/.profile"
            ;;
    esac

    local export_line='export MANIFEST_STATE_ROOT="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"'
    # shellcheck disable=SC2034
    SHELL_PROFILE_FILE="$profile_file"

    mkdir -p "$(dirname "$profile_file")"
    touch "$profile_file"

    if grep -Fq "MANIFEST_STATE_ROOT" "$profile_file" 2> /dev/null; then
        print_info "MANIFEST_STATE_ROOT already configured in $profile_file"
    else
        {
            echo ""
            echo "# Manifest runtime state root (managed by bootstrap.sh)"
            echo "$export_line"
        } >> "$profile_file"
        print_success "Added MANIFEST_STATE_ROOT export to $profile_file"
    fi
}

# Prepare shared runtime state directories under ~/.manifest
setup_manifest_state_dirs() {
    print_step "Preparing shared state directories in $MANIFEST_STATE_DIR..."

    local state_dirs=(
        "$MANIFEST_STATE_DIR"
        "$MANIFEST_STATE_DIR/orchestration"
        "$MANIFEST_OUTPUT_DIR"
        "$MANIFEST_TMP_DIR"
        "$MANIFEST_STATE_DIR/claude"
        "$MANIFEST_STATE_DIR/claude/outputs"
        "$MANIFEST_STATE_DIR/claude/tmp"
        "$MANIFEST_STATE_DIR/gemini"
        "$MANIFEST_STATE_DIR/gemini/outputs"
        "$MANIFEST_STATE_DIR/gemini/tmp"
        "$MANIFEST_STATE_DIR/cursor"
        "$MANIFEST_STATE_DIR/cursor/outputs"
        "$MANIFEST_STATE_DIR/cursor/tmp"
        "$MANIFEST_STATE_DIR/codex"
        "$MANIFEST_STATE_DIR/codex/outputs"
        "$MANIFEST_STATE_DIR/codex/tmp"
        "$MANIFEST_STATE_DIR/codex/sessions"
    )

    for dir in "${state_dirs[@]}"; do
        mkdir -p "$dir"
        chmod 700 "$dir" 2> /dev/null || true
    done

    print_success "State directories ready under $MANIFEST_STATE_DIR (including codex/sessions)"
}

# Shared asset linking and MCP setup functions are sourced from:
# - bootstrap/lib/common.sh
# - bootstrap/lib/mcp.sh

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
