#!/bin/bash

# MCP management helpers for bootstrap.sh. This file is sourced, not executed.

# Write Cursor MCP server configuration file.
# Cursor reads mcp.json from ~/.cursor (global) and supports OAuth-capable HTTP servers.
configure_cursor_mcp_config() {
    local cursor_mcp_file="$CURSOR_TARGET_DIR/mcp.json"
    mkdir -p "$CURSOR_TARGET_DIR"

    cat > "$cursor_mcp_file" << EOF
{
  "mcpServers": {
    "sentry": {
      "url": "$MCP_SENTRY_URL"
    },
    "context7": {
      "url": "$MCP_CONTEXT7_URL"
    },
    "linear": {
      "url": "$MCP_LINEAR_URL"
    }
  }
}
EOF

    chmod 600 "$cursor_mcp_file" 2> /dev/null || true
    print_success "Configured Cursor MCP servers in $cursor_mcp_file"
}

# Fallback writer for Gemini MCP server entries.
# Uses jq when available to merge without clobbering unrelated settings.
ensure_gemini_mcp_server_in_settings() {
    local name="$1"
    local url="$2"
    local settings_file="$GEMINI_TARGET_DIR/settings.json"
    local tmp_file=""

    mkdir -p "$GEMINI_TARGET_DIR"
    if [[ ! -f "$settings_file" ]]; then
        echo "{}" > "$settings_file"
    fi

    if ! command_exists jq; then
        return 1
    fi

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/gemini-mcp.XXXXXX")"
    if jq \
        --arg name "$name" \
        --arg url "$url" \
        '.mcpServers = (.mcpServers // {}) | .mcpServers[$name] = {"url": $url, "type": "http"}' \
        "$settings_file" > "$tmp_file"; then
        mv "$tmp_file" "$settings_file"
        chmod 600 "$settings_file" 2> /dev/null || true
        return 0
    fi

    rm -f "$tmp_file"
    return 1
}

# Install/update one Claude MCP server (OAuth-capable HTTP transport).
install_claude_mcp_server() {
    local name="$1"
    local url="$2"

    # Remove existing definitions across scopes to avoid name collisions.
    claude mcp remove "$name" > /dev/null 2>&1 || true
    claude mcp remove --scope "$CLAUDE_MCP_SCOPE" "$name" > /dev/null 2>&1 || true
    if claude mcp add --scope "$CLAUDE_MCP_SCOPE" --transport http "$name" "$url" > /dev/null 2>&1; then
        print_success "Claude MCP configured: $name -> $url"
        return 0
    fi

    print_warning "Failed to configure Claude MCP server '$name'"
    return 1
}

# Install/update one Gemini MCP server (OAuth-capable HTTP transport).
install_gemini_mcp_server() {
    local name="$1"
    local url="$2"

    # Remove existing definitions across scopes to avoid name collisions.
    gemini mcp remove --scope user "$name" > /dev/null 2>&1 || true
    gemini mcp remove --scope project "$name" > /dev/null 2>&1 || true
    gemini mcp remove --scope "$GEMINI_MCP_SCOPE" "$name" > /dev/null 2>&1 || true
    if gemini mcp add --scope "$GEMINI_MCP_SCOPE" --transport http "$name" "$url" > /dev/null 2>&1; then
        print_success "Gemini MCP configured: $name -> $url"
        return 0
    fi

    if ensure_gemini_mcp_server_in_settings "$name" "$url"; then
        print_warning "Gemini CLI MCP add failed; wrote '$name' to settings.json fallback"
        return 0
    fi

    print_warning "Failed to configure Gemini MCP server '$name'"
    return 1
}

# Install/update one Codex MCP server (OAuth-capable streamable HTTP transport).
install_codex_mcp_server() {
    local name="$1"
    local url="$2"

    codex mcp remove "$name" > /dev/null 2>&1 || true
    if codex mcp add "$name" --url "$url" > /dev/null 2>&1; then
        print_success "Codex MCP configured: $name -> $url"
        return 0
    fi

    print_warning "Failed to configure Codex MCP server '$name'"
    return 1
}

# Configure default MCP servers for enabled agents.
# Servers are OAuth-capable by default:
# - sentry:   https://mcp.sentry.dev/mcp
# - context7: https://mcp.context7.com/mcp/oauth
# - linear:   https://mcp.linear.app/mcp
install_mcp_servers() {
    print_header "Configuring MCP Servers"

    local mcp_names=("sentry" "context7" "linear")
    local mcp_urls=("$MCP_SENTRY_URL" "$MCP_CONTEXT7_URL" "$MCP_LINEAR_URL")
    local failures=0
    local i

    echo "OAuth-capable MCP endpoints:"
    echo "  sentry:   $MCP_SENTRY_URL"
    echo "  context7: $MCP_CONTEXT7_URL"
    echo "  linear:   $MCP_LINEAR_URL"
    echo ""

    if [[ "$ENABLE_CLAUDE" == true ]]; then
        if command_exists claude; then
            print_step "Configuring Claude MCP servers..."
            for i in "${!mcp_names[@]}"; do
                install_claude_mcp_server "${mcp_names[$i]}" "${mcp_urls[$i]}" || failures=$((failures + 1))
            done
        else
            print_warning "Claude CLI unavailable; skipped Claude MCP setup"
        fi
    else
        print_info "Claude is disabled; skipped Claude MCP setup"
    fi

    if [[ "$ENABLE_GEMINI" == true ]]; then
        if command_exists gemini; then
            print_step "Configuring Gemini MCP servers..."
            for i in "${!mcp_names[@]}"; do
                install_gemini_mcp_server "${mcp_names[$i]}" "${mcp_urls[$i]}" || failures=$((failures + 1))
            done
        else
            print_warning "Gemini CLI unavailable; skipped Gemini MCP setup"
        fi
    else
        print_info "Gemini is disabled; skipped Gemini MCP setup"
    fi

    if [[ "$ENABLE_CODEX" == true ]]; then
        if command_exists codex; then
            print_step "Configuring Codex MCP servers..."
            for i in "${!mcp_names[@]}"; do
                install_codex_mcp_server "${mcp_names[$i]}" "${mcp_urls[$i]}" || failures=$((failures + 1))
            done
        else
            print_warning "Codex CLI unavailable; skipped Codex MCP setup"
        fi
    else
        print_info "Codex is disabled; skipped Codex MCP setup"
    fi

    if [[ "$ENABLE_CURSOR" == true ]]; then
        print_step "Configuring Cursor MCP servers..."
        configure_cursor_mcp_config || failures=$((failures + 1))
    else
        print_info "Cursor is disabled; skipped Cursor MCP setup"
    fi

    echo ""
    echo -e "${BOLD}OAuth Notes:${NC}"
    echo "  Claude: OAuth is completed on first use of each MCP server."
    echo "  Gemini: OAuth is completed on first use of each MCP server."
    echo "  Codex:  Run 'codex mcp login <server>' to pre-authenticate (optional)."
    echo "          Example: codex mcp login sentry"
    echo ""

    if [[ $failures -eq 0 ]]; then
        print_success "MCP server setup completed"
    else
        print_warning "MCP server setup completed with $failures warning(s)"
    fi
}
