#!/bin/bash

# Bootstrap argument/config helpers for bootstrap.sh. This file is sourced, not executed.

set_bootstrap_defaults() {
    # Flags
    SKIP_INSTALL=false
    SKIP_AUTH=false
    INSTALL_MCP=false
    FORCE=false
    RECONFIGURE=false

    # MCP scope defaults (server URLs are parsed from configs/claude/config/mcp_servers.yml)
    CLAUDE_MCP_SCOPE="${CLAUDE_MCP_SCOPE:-user}" # local | user | project
    GEMINI_MCP_SCOPE="${GEMINI_MCP_SCOPE:-user}" # user | project

    if [[ "$CLAUDE_MCP_SCOPE" != "local" && "$CLAUDE_MCP_SCOPE" != "user" && "$CLAUDE_MCP_SCOPE" != "project" ]]; then
        CLAUDE_MCP_SCOPE="user"
    fi
    if [[ "$GEMINI_MCP_SCOPE" != "user" && "$GEMINI_MCP_SCOPE" != "project" ]]; then
        GEMINI_MCP_SCOPE="user"
    fi

    # Service toggles (default: all enabled, gh/glab auto-detect, browser-use disabled by default)
    ENABLE_CLAUDE=true
    ENABLE_GEMINI=true
    ENABLE_CURSOR=true
    ENABLE_CODEX=true
    ENABLE_ANTIGRAVITY=true
    ENABLE_GRAPHIFY=true
    ENABLE_SKILLCLAW=false
    ENABLE_BROWSER_USE=false
    ENABLE_SMOKE=false
    ENABLE_GH="auto"
    ENABLE_GLAB="auto"

    # Track if user explicitly set toggles
    CLAUDE_SET=false
    GEMINI_SET=false
    CURSOR_SET=false
    CODEX_SET=false
    ANTIGRAVITY_SET=false
    GRAPHIFY_SET=false
    SKILLCLAW_SET=false
    BROWSER_USE_SET=false
    SMOKE_SET=false
    GH_SET=false
    GLAB_SET=false
}

print_bootstrap_help() {
    local script_name="${1:-$0}"

    echo "AI Agent Support Framework Bootstrap"
    echo "Supports: macOS (Intel/Apple Silicon), Linux (Debian, RHEL, Arch, etc.)"
    echo ""
    echo "Usage: $script_name [options]"
    echo ""
    echo "Service Toggles:"
    echo "  --enable-claude     Enable Claude CLI (default: enabled)"
    echo "  --disable-claude    Disable Claude CLI"
    echo "  --enable-gemini     Enable Gemini CLI (default: enabled)"
    echo "  --disable-gemini    Disable Gemini CLI"
    echo "  --enable-cursor     Enable Cursor agent (default: enabled)"
    echo "  --disable-cursor    Disable Cursor agent"
    echo "  --enable-codex      Enable Codex CLI (default: enabled)"
    echo "  --disable-codex     Disable Codex CLI"
    echo "  --enable-antigravity   Enable Antigravity IDE (default: enabled)"
    echo "  --disable-antigravity  Disable Antigravity IDE"
    echo "  --enable-graphify      Enable Graphify knowledge-graph CLI (default: enabled)"
    echo "  --disable-graphify     Disable Graphify knowledge-graph CLI"
    echo "  --enable-skillclaw     Enable SkillClaw session capture (default: disabled)"
    echo "  --disable-skillclaw    Disable SkillClaw session capture"
    echo "  --enable-browser-use   Enable browser-use E2E testing (default: disabled)"
    echo "  --disable-browser-use  Disable browser-use E2E testing"
    echo "  --enable-smoke         Install smoke-test deps: Playwright+Chromium (default: disabled)"
    echo "  --disable-smoke        Skip smoke-test dependency install"
    echo "  --enable-gh         Enable GitHub CLI (default: auto-detect)"
    echo "  --disable-gh        Disable GitHub CLI"
    echo "  --enable-glab       Enable GitLab CLI (default: auto-detect)"
    echo "  --disable-glab      Disable GitLab CLI"
    echo ""
    echo "Other Options:"
    echo "  --skip-install      Skip CLI tool installation"
    echo "  --skip-auth         Skip authentication checks"
    echo "  --install-mcp       Configure MCP servers (interactive selection from registry)"
    echo "  --force             Overwrite existing ~/.claude without prompting"
    echo "  --reconfigure       Only update service toggles (skip full setup)"
    echo ""
    echo "Examples:"
    echo "  $script_name                              # Full setup with all services"
    echo "  $script_name --disable-cursor             # Setup without Cursor"
    echo "  $script_name --disable-codex              # Setup without Codex"
    echo "  $script_name --enable-gh --enable-glab    # Explicitly enable Git CLIs"
    echo "  $script_name --install-mcp                # Configure MCP servers for enabled agents"
    echo "  $script_name --reconfigure --disable-gemini  # Just disable Gemini"
    echo "  $script_name --skip-auth                  # Setup without authentication checks"
}

parse_bootstrap_args() {
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
            --enable-codex)
                ENABLE_CODEX=true
                CODEX_SET=true
                shift
                ;;
            --disable-codex)
                ENABLE_CODEX=false
                CODEX_SET=true
                shift
                ;;
            --enable-antigravity)
                ENABLE_ANTIGRAVITY=true
                ANTIGRAVITY_SET=true
                shift
                ;;
            --disable-antigravity)
                ENABLE_ANTIGRAVITY=false
                ANTIGRAVITY_SET=true
                shift
                ;;
            --enable-graphify)
                ENABLE_GRAPHIFY=true
                GRAPHIFY_SET=true
                shift
                ;;
            --disable-graphify)
                ENABLE_GRAPHIFY=false
                GRAPHIFY_SET=true
                shift
                ;;
            --enable-skillclaw)
                ENABLE_SKILLCLAW=true
                SKILLCLAW_SET=true
                shift
                ;;
            --disable-skillclaw)
                ENABLE_SKILLCLAW=false
                SKILLCLAW_SET=true
                shift
                ;;
            --enable-browser-use)
                ENABLE_BROWSER_USE=true
                BROWSER_USE_SET=true
                shift
                ;;
            --disable-browser-use)
                ENABLE_BROWSER_USE=false
                BROWSER_USE_SET=true
                shift
                ;;
            --enable-smoke)
                ENABLE_SMOKE=true
                SMOKE_SET=true
                shift
                ;;
            --disable-smoke)
                ENABLE_SMOKE=false
                SMOKE_SET=true
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
                # shellcheck disable=SC2034
                SKIP_INSTALL=true
                shift
                ;;
            --skip-auth)
                # shellcheck disable=SC2034
                SKIP_AUTH=true
                shift
                ;;
            --install-mcp)
                # shellcheck disable=SC2034
                INSTALL_MCP=true
                shift
                ;;
            --force)
                # shellcheck disable=SC2034
                FORCE=true
                shift
                ;;
            --reconfigure)
                # shellcheck disable=SC2034
                RECONFIGURE=true
                shift
                ;;
            -h | --help)
                print_bootstrap_help "${BOOTSTRAP_SCRIPT_NAME:-$0}"
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}
# Parse service configuration using awk (single pass)
parse_services_config() {
    FILE_CLAUDE=""
    FILE_GEMINI=""
    FILE_CURSOR=""
    FILE_CODEX=""
    FILE_ANTIGRAVITY=""
    FILE_GRAPHIFY=""
    FILE_SKILLCLAW=""
    FILE_BROWSER_USE=""
    FILE_SMOKE=""
    FILE_GH=""
    FILE_GLAB=""

    if [[ -f "$SERVICES_CONFIG" ]]; then
        local config_settings
        config_settings=$(awk '
            BEGIN { section=""; subsection="" }
            /^[[:space:]]*claude:/ { section="claude"; subsection="" }
            /^[[:space:]]*gemini:/ { section="gemini"; subsection="" }
            /^[[:space:]]*cursor:/ { section="cursor"; subsection="" }
            /^[[:space:]]*codex:/ { section="codex"; subsection="" }
            /^[[:space:]]*antigravity:/ { section="antigravity"; subsection="" }
            /^[[:space:]]*graphify:/ { section="graphify"; subsection="" }
            /^[[:space:]]*skillclaw:/ { section="skillclaw"; subsection="" }
            /^[[:space:]]*browser_use:/ { section="browser_use"; subsection="" }
            /^[[:space:]]*smoke:/ { section="smoke"; subsection="" }
            /^[[:space:]]*git_cli:/ { section="git_cli"; subsection="" }
            /^[[:space:]]*github:/ { if (section == "git_cli") subsection="github" }
            /^[[:space:]]*gitlab:/ { if (section == "git_cli") subsection="gitlab" }
            /^[[:space:]]*enabled:[[:space:]]*true/ {
                if (section == "claude") print "FILE_CLAUDE=true"
                if (section == "gemini") print "FILE_GEMINI=true"
                if (section == "cursor") print "FILE_CURSOR=true"
                if (section == "codex") print "FILE_CODEX=true"
                if (section == "antigravity") print "FILE_ANTIGRAVITY=true"
                if (section == "graphify") print "FILE_GRAPHIFY=true"
                if (section == "skillclaw") print "FILE_SKILLCLAW=true"
                if (section == "browser_use") print "FILE_BROWSER_USE=true"
                if (section == "smoke") print "FILE_SMOKE=true"
                if (section == "git_cli" && subsection == "github") print "FILE_GH=true"
                if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=true"
            }
            /^[[:space:]]*enabled:[[:space:]]*false/ {
                if (section == "claude") print "FILE_CLAUDE=false"
                if (section == "gemini") print "FILE_GEMINI=false"
                if (section == "cursor") print "FILE_CURSOR=false"
                if (section == "codex") print "FILE_CODEX=false"
                if (section == "antigravity") print "FILE_ANTIGRAVITY=false"
                if (section == "graphify") print "FILE_GRAPHIFY=false"
                if (section == "skillclaw") print "FILE_SKILLCLAW=false"
                if (section == "browser_use") print "FILE_BROWSER_USE=false"
                if (section == "smoke") print "FILE_SMOKE=false"
                if (section == "git_cli" && subsection == "github") print "FILE_GH=false"
                if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=false"
            }
            /^[[:space:]]*enabled:[[:space:]]*auto/ {
                if (section == "git_cli" && subsection == "github") print "FILE_GH=auto"
                if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=auto"
            }
        ' "$SERVICES_CONFIG")

        if [[ -n "$config_settings" ]]; then
            while IFS= read -r line; do
                if [[ -n "$line" ]]; then
                    key="${line%%=*}"
                    val="${line#*=}"
                    val="${val%\"}"
                    val="${val#\"}"
                    case "$key" in
                        FILE_CLAUDE | FILE_GEMINI | FILE_CURSOR | FILE_CODEX | FILE_ANTIGRAVITY | FILE_GRAPHIFY | FILE_SKILLCLAW | FILE_BROWSER_USE | FILE_SMOKE | FILE_GH | FILE_GLAB)
                            printf -v "$key" "%s" "$val"
                            ;;
                    esac
                fi
            done <<< "$config_settings"
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

        if [[ "$CODEX_SET" == false && -n "$FILE_CODEX" ]]; then
            ENABLE_CODEX=$FILE_CODEX
        fi

        if [[ "$ANTIGRAVITY_SET" == false && -n "$FILE_ANTIGRAVITY" ]]; then
            ENABLE_ANTIGRAVITY=$FILE_ANTIGRAVITY
        fi

        if [[ "$GRAPHIFY_SET" == false && -n "$FILE_GRAPHIFY" ]]; then
            ENABLE_GRAPHIFY=$FILE_GRAPHIFY
        fi

        if [[ "$SKILLCLAW_SET" == false && -n "$FILE_SKILLCLAW" ]]; then
            ENABLE_SKILLCLAW=$FILE_SKILLCLAW
        fi

        if [[ "$BROWSER_USE_SET" == false && -n "$FILE_BROWSER_USE" ]]; then
            ENABLE_BROWSER_USE=$FILE_BROWSER_USE
        fi

        if [[ "$SMOKE_SET" == false && -n "$FILE_SMOKE" ]]; then
            ENABLE_SMOKE=$FILE_SMOKE
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
      - fable    # Top tier (security-critical tasks)

  # Gemini CLI - Google's AI assistant
  # Install: npm install -g @google/gemini-cli
  gemini:
    enabled: $ENABLE_GEMINI
    command: gemini
    description: "Broad knowledge, creative solutions, research"
    model_tiers:
      - flash    # Fast (default)
      - pro      # Advanced

  # Cursor Agent - headless CLI for code analysis
  # Install: curl https://cursor.com/install -fsS | bash
  cursor:
    enabled: $ENABLE_CURSOR
    command: cursor-agent
    description: "IDE-integrated context, code-specific analysis"
    model_tiers:
      - mini     # Lightweight
      - flash    # Balanced (default)
      - advanced  # Maximum capability

  # Codex CLI - OpenAI terminal coding agent
  # Install: npm install -g @openai/codex
  codex:
    enabled: $ENABLE_CODEX
    command: codex
    description: "Terminal coding assistant for codebase edits and automation"
    model_tiers:
      - mini     # Lightweight
      - flash    # Balanced (default)
      - advanced  # Maximum capability
      - auto     # Use Codex config default model
    auth:
      - OPENAI_API_KEY
      - ~/.codex/auth.json

  # Antigravity CLI - Google's agentic IDE CLI (agy)
  # Install: via the Antigravity IDE, then run: agy install
  antigravity:
    enabled: $ENABLE_ANTIGRAVITY
    command: agy
    description: "Antigravity CLI for cross-vendor verification (Gemini/Claude catalog)"
    model_tiers:
      - mini     # Lightweight
      - flash    # Balanced (default)
      - advanced  # Maximum capability

  # Graphify - AI-powered knowledge-graph generator (/graphify skill + CLI)
  # Install: uv tool install graphifyy (handled by bootstrap/lib/install.sh)
  # Default backend is host-agent (uses the running assistant as the LLM; no key required).
  graphify:
    enabled: $ENABLE_GRAPHIFY
    command: graphify
    description: "Maps a codebase/docs into a queryable knowledge graph (/graphify)"

  # SkillClaw - evolves SKILL.md skills from Claude Code transcripts (proxy-free)
  # Managed by bootstrap/lib/skillclaw.sh; no install, no daemon, no proxy.
  skillclaw:
    enabled: ${ENABLE_SKILLCLAW:-false}
    description: "Evolves skills from transcripts into review PRs via /skill-evolve (opt-in)"
    storage: ~/.skillclaw

  # browser-use - AI-powered E2E browser testing agent
  browser_use:
    enabled: ${ENABLE_BROWSER_USE:-false}
    command: browser-use
    description: "AI-powered E2E browser testing via browser-use"

  # smoke-manage runtime deps (Playwright + Chromium) for declarative E2E smoke tests
  smoke:
    enabled: ${ENABLE_SMOKE:-false}
    command: smoke_test.py
    description: "Declarative tiered E2E smoke tests (opt-in Playwright + Chromium)"

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
