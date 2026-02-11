#!/bin/bash

# MCP management helpers for bootstrap.sh. This file is sourced, not executed.

# ---------------------------------------------------------------------------
# Registry parsing
# ---------------------------------------------------------------------------

# Parse mcp_servers.yml into parallel arrays:
#   MCP_SERVER_NAMES[i]      — server key (e.g. "sentry")
#   MCP_SERVER_URLS[i]       — endpoint URL
#   MCP_SERVER_TRANSPORTS[i] — transport type (http, sse)
#   MCP_SERVER_PURPOSES[i]   — human-readable purpose string
#
# Primary: python3 + PyYAML.  Fallback: awk on the flat YAML structure.
# Expects SCRIPT_DIR to be set by the caller (bootstrap.sh).
parse_mcp_registry() {
    local yaml_file="$SCRIPT_DIR/configs/claude/config/mcp_servers.yml"

    MCP_SERVER_NAMES=()
    MCP_SERVER_URLS=()
    MCP_SERVER_TRANSPORTS=()
    MCP_SERVER_PURPOSES=()

    if [[ ! -f "$yaml_file" ]]; then
        print_warning "MCP registry not found: $yaml_file"
        return 1
    fi

    local parsed=""

    # --- Primary: python3 ---
    if command_exists python3; then
        parsed=$(python3 -c "
import yaml, sys
try:
    data = yaml.safe_load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
servers = data.get('mcp_servers', {})
for name, info in servers.items():
    url = info.get('url', '')
    transport = info.get('transport', 'http')
    purpose = info.get('purpose', '')
    print(f'{name}|{url}|{transport}|{purpose}')
" "$yaml_file" 2> /dev/null)
    fi

    # --- Fallback: awk ---
    if [[ -z "$parsed" ]]; then
        parsed=$(awk '
            /^[[:space:]]*[a-zA-Z0-9_-]+:/ && !/^[[:space:]]*mcp_servers:/ && !/^[[:space:]]*(url|transport|oauth|purpose|note):/ {
                gsub(/^[[:space:]]+|:[[:space:]]*$/, "")
                name = $0; transport = "http"
            }
            /^[[:space:]]*url:/ {
                val = $0
                sub(/^[[:space:]]*url:[[:space:]]*"?/, "", val)
                sub(/"[[:space:]]*$/, "", val)
                url = val
            }
            /^[[:space:]]*transport:/ {
                val = $0
                sub(/^[[:space:]]*transport:[[:space:]]*"?/, "", val)
                sub(/"[[:space:]]*$/, "", val)
                transport = val
            }
            /^[[:space:]]*purpose:/ {
                val = $0
                sub(/^[[:space:]]*purpose:[[:space:]]*"?/, "", val)
                sub(/"[[:space:]]*$/, "", val)
                purpose = val
                if (name != "" && url != "") {
                    print name "|" url "|" transport "|" purpose
                }
                name = ""; url = ""; transport = "http"; purpose = ""
            }
        ' "$yaml_file" 2> /dev/null)
    fi

    if [[ -z "$parsed" ]]; then
        print_warning "Failed to parse MCP registry from $yaml_file"
        return 1
    fi

    local line
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local name url transport purpose
        name="${line%%|*}"
        line="${line#*|}"
        url="${line%%|*}"
        line="${line#*|}"
        transport="${line%%|*}"
        purpose="${line#*|}"
        MCP_SERVER_NAMES+=("$name")
        MCP_SERVER_URLS+=("$url")
        MCP_SERVER_TRANSPORTS+=("$transport")
        MCP_SERVER_PURPOSES+=("$purpose")
    done <<< "$parsed"

    if [[ ${#MCP_SERVER_NAMES[@]} -eq 0 ]]; then
        print_warning "No MCP servers found in registry"
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------

# Prompt the user to select which MCP servers to install.
# Populates MCP_SELECTED_INDICES with the chosen array positions.
# If FORCE is true, all servers are selected without prompting.
prompt_mcp_selection() {
    MCP_SELECTED_INDICES=()

    if [[ "$FORCE" == true ]]; then
        local j
        for j in "${!MCP_SERVER_NAMES[@]}"; do
            MCP_SELECTED_INDICES+=("$j")
        done
        return 0
    fi

    echo "Select which MCP servers to install:"
    echo ""

    local i
    for i in "${!MCP_SERVER_NAMES[@]}"; do
        if prompt_yes_no "  Install ${MCP_SERVER_NAMES[$i]}? (${MCP_SERVER_PURPOSES[$i]})" "y"; then
            MCP_SELECTED_INDICES+=("$i")
        fi
    done
    echo ""

    if [[ ${#MCP_SELECTED_INDICES[@]} -eq 0 ]]; then
        print_info "No MCP servers selected"
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Cursor MCP config writer (dynamic)
# ---------------------------------------------------------------------------

# Write Cursor MCP server configuration file.
# Cursor reads mcp.json from ~/.cursor (global) and supports OAuth-capable HTTP servers.
# Only writes selected servers.
configure_cursor_mcp_config() {
    local cursor_mcp_file="$CURSOR_TARGET_DIR/mcp.json"
    mkdir -p "$CURSOR_TARGET_DIR"

    # Build JSON dynamically from selected servers
    local json_entries=""
    local first=true
    local idx
    for idx in "${MCP_SELECTED_INDICES[@]}"; do
        local name="${MCP_SERVER_NAMES[$idx]}"
        local url="${MCP_SERVER_URLS[$idx]}"
        if [[ "$first" == true ]]; then
            first=false
        else
            json_entries+=","
        fi
        # Use printf to safely construct each entry (names/urls are from our YAML, not user input)
        json_entries+=$'\n'"    \"${name}\": {"$'\n'"      \"url\": \"${url}\""$'\n'"    }"
    done

    cat > "$cursor_mcp_file" << EOF
{
  "mcpServers": {${json_entries}
  }
}
EOF

    chmod 600 "$cursor_mcp_file" 2> /dev/null || true
    print_success "Configured Cursor MCP servers in $cursor_mcp_file"
}

# ---------------------------------------------------------------------------
# Per-agent installers (unchanged)
# ---------------------------------------------------------------------------

# Fallback writer for Gemini MCP server entries.
# Uses jq when available to merge without clobbering unrelated settings.
ensure_gemini_mcp_server_in_settings() {
    local name="$1"
    local url="$2"
    local transport="${3:-http}"
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
        --arg transport "$transport" \
        '.mcpServers = (.mcpServers // {}) | .mcpServers[$name] = {"url": $url, "type": $transport}' \
        "$settings_file" > "$tmp_file"; then
        mv "$tmp_file" "$settings_file"
        chmod 600 "$settings_file" 2> /dev/null || true
        return 0
    fi

    rm -f "$tmp_file"
    return 1
}

# Install/update one Claude MCP server.
install_claude_mcp_server() {
    local name="$1"
    local url="$2"
    local transport="${3:-http}"

    # Remove existing definitions across scopes to avoid name collisions.
    claude mcp remove "$name" > /dev/null 2>&1 || true
    claude mcp remove --scope "$CLAUDE_MCP_SCOPE" "$name" > /dev/null 2>&1 || true
    if claude mcp add --scope "$CLAUDE_MCP_SCOPE" --transport "$transport" "$name" "$url" > /dev/null 2>&1; then
        print_success "Claude MCP configured: $name -> $url ($transport)"
        return 0
    fi

    print_warning "Failed to configure Claude MCP server '$name'"
    return 1
}

# Install/update one Gemini MCP server.
install_gemini_mcp_server() {
    local name="$1"
    local url="$2"
    local transport="${3:-http}"

    # Remove existing definitions across scopes to avoid name collisions.
    gemini mcp remove --scope user "$name" > /dev/null 2>&1 || true
    gemini mcp remove --scope project "$name" > /dev/null 2>&1 || true
    gemini mcp remove --scope "$GEMINI_MCP_SCOPE" "$name" > /dev/null 2>&1 || true
    if gemini mcp add --scope "$GEMINI_MCP_SCOPE" --transport "$transport" "$name" "$url" > /dev/null 2>&1; then
        print_success "Gemini MCP configured: $name -> $url ($transport)"
        return 0
    fi

    if ensure_gemini_mcp_server_in_settings "$name" "$url" "$transport"; then
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

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Configure MCP servers for enabled agents.
# Reads the server registry from mcp_servers.yml, prompts the user to select
# which servers to install (or auto-selects all when --force is set), then
# configures each enabled agent with the selected servers.
install_mcp_servers() {
    print_header "Configuring MCP Servers"

    # 1. Parse YAML registry
    if ! parse_mcp_registry; then
        print_warning "Skipping MCP setup — could not read server registry"
        return 1
    fi

    # 2. Show available servers
    echo "Available MCP servers (from mcp_servers.yml):"
    local i
    for i in "${!MCP_SERVER_NAMES[@]}"; do
        echo "  ${MCP_SERVER_NAMES[$i]}:  ${MCP_SERVER_URLS[$i]}"
        echo "          ${MCP_SERVER_PURPOSES[$i]}"
    done
    echo ""

    # 3. Prompt for selection (or auto-select with --force)
    if ! prompt_mcp_selection; then
        return 0
    fi

    local selected_count=${#MCP_SELECTED_INDICES[@]}
    print_step "Installing $selected_count server(s)..."
    echo ""

    local failures=0
    local idx

    # 4. Install selected servers to each enabled agent
    if [[ "$ENABLE_CLAUDE" == true ]]; then
        if command_exists claude; then
            print_step "Configuring Claude MCP servers..."
            for idx in "${MCP_SELECTED_INDICES[@]}"; do
                install_claude_mcp_server "${MCP_SERVER_NAMES[$idx]}" "${MCP_SERVER_URLS[$idx]}" "${MCP_SERVER_TRANSPORTS[$idx]}" || failures=$((failures + 1))
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
            for idx in "${MCP_SELECTED_INDICES[@]}"; do
                install_gemini_mcp_server "${MCP_SERVER_NAMES[$idx]}" "${MCP_SERVER_URLS[$idx]}" "${MCP_SERVER_TRANSPORTS[$idx]}" || failures=$((failures + 1))
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
            for idx in "${MCP_SELECTED_INDICES[@]}"; do
                install_codex_mcp_server "${MCP_SERVER_NAMES[$idx]}" "${MCP_SERVER_URLS[$idx]}" "${MCP_SERVER_TRANSPORTS[$idx]}" || failures=$((failures + 1))
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

    # 5. OAuth notes & summary
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
