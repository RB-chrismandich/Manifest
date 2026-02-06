#!/bin/bash
# System Health Check for Parallel Agent Orchestration
# Usage: ./check_status.sh [--verbose]

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${BLUE}  Parallel Agent System Health Check${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Check if services.yml exists
echo -e "${BOLD}Configuration:${NC}"
if [[ -f ~/.claude/config/services.yml ]]; then
    echo -e "  ${GREEN}✓${NC} services.yml found"

    # Parse enabled services using grep (more portable than yq)
    claude_enabled=$(grep -A1 "^  claude:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    gemini_enabled=$(grep -A1 "^  gemini:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')
    cursor_enabled=$(grep -A1 "^  cursor:" ~/.claude/config/services.yml | grep "enabled:" | awk '{print $2}')

    enabled_count=0
    [[ "$claude_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
    [[ "$gemini_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))
    [[ "$cursor_enabled" == "true" ]] && enabled_count=$((enabled_count + 1))

    echo ""
    echo -e "${BOLD}Enabled Services (${enabled_count}/3):${NC}"

    if [[ "$claude_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Claude"
    else
        echo -e "  ${RED}✗${NC} Claude (disabled)"
    fi

    if [[ "$gemini_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Gemini"
    else
        echo -e "  ${RED}✗${NC} Gemini (disabled)"
    fi

    if [[ "$cursor_enabled" == "true" ]]; then
        echo -e "  ${GREEN}✓${NC} Cursor"
    else
        echo -e "  ${RED}✗${NC} Cursor (disabled)"
    fi

    if [[ $enabled_count -lt 2 ]]; then
        echo ""
        echo -e "  ${YELLOW}⚠${NC}  Warning: Minimum 2 services needed for parallel orchestration"
        echo -e "  ${BLUE}→${NC} Fix: ./bootstrap.sh --reconfigure --enable-claude --enable-gemini"
    fi
else
    echo -e "  ${RED}✗${NC} services.yml not found"
    echo -e "  ${BLUE}→${NC} Run: ./bootstrap.sh"
fi

echo ""

# Check CLI installations
echo -e "${BOLD}CLI Tools:${NC}"

claude_installed=false
if command -v claude &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Claude CLI installed"
    claude_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which claude)"
        echo -e "    Version:  $(claude --version 2> /dev/null || echo 'unknown')"
    fi
else
    echo -e "  ${RED}✗${NC} Claude CLI not installed"
    echo -e "    ${BLUE}→${NC} Install: npm install -g @anthropic-ai/claude-code"
fi

gemini_installed=false
if command -v gemini &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Gemini CLI installed"
    gemini_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which gemini)"
        echo -e "    Version:  $(gemini --version 2> /dev/null || echo 'unknown')"
    fi
else
    echo -e "  ${RED}✗${NC} Gemini CLI not installed"
    echo -e "    ${BLUE}→${NC} Install: npm install -g @google/gemini-cli"
fi

cursor_installed=false
if command -v cursor &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Cursor CLI available"
    cursor_installed=true
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    Location: $(which cursor)"
    fi
else
    echo -e "  ${YELLOW}○${NC} Cursor not available (optional)"
    if [[ "$VERBOSE" == true ]]; then
        echo -e "    ${BLUE}→${NC} Download: https://cursor.sh"
    fi
fi

echo ""

# Check authentication
echo -e "${BOLD}Authentication:${NC}"

if [[ "$claude_installed" == true ]]; then
    # Add timeout to avoid hanging
    if timeout 3 claude auth status &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Claude authenticated"
    else
        echo -e "  ${YELLOW}?${NC} Claude authentication unknown (check timeout)"
        echo -e "    ${BLUE}→${NC} Verify: claude auth status"
    fi
fi

if [[ "$gemini_installed" == true ]]; then
    # Add timeout to avoid hanging
    if timeout 3 gemini auth status &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Gemini authenticated"
    else
        echo -e "  ${YELLOW}?${NC} Gemini authentication unknown (check timeout)"
        echo -e "    ${BLUE}→${NC} Verify: gemini auth status"
    fi
fi

echo ""

# Overall status
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Overall Status:${NC}"

working_agents=0
[[ "$claude_installed" == true && "$claude_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$gemini_installed" == true && "$gemini_enabled" == "true" ]] && working_agents=$((working_agents + 1))
[[ "$cursor_installed" == true && "$cursor_enabled" == "true" ]] && working_agents=$((working_agents + 1))

if [[ $working_agents -ge 2 ]]; then
    echo -e "  ${GREEN}✓${NC} System ready for parallel orchestration (${working_agents} agents available)"
elif [[ $working_agents -eq 1 ]]; then
    echo -e "  ${YELLOW}⚠${NC}  Limited functionality (only ${working_agents} agent available)"
    echo -e "  ${BLUE}→${NC} Enable/install at least 2 agents for full features"
else
    echo -e "  ${RED}✗${NC} System not operational (no agents available)"
    echo -e "  ${BLUE}→${NC} Run: ./bootstrap.sh"
fi

echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Quick test option
if [[ $working_agents -ge 1 ]]; then
    echo -e "${BOLD}Quick Test:${NC}"
    echo -e "  ~/.claude/scripts/parallel_agent.sh --json 'What is 2+2?'"
    echo ""
fi

echo -e "${BOLD}Documentation:${NC}"
echo -e "  Troubleshooting: docs/TROUBLESHOOTING.md"
echo -e "  Configuration:   docs/CONFIGURATION.md"
echo -e "  Getting Started: docs/GETTING_STARTED.md"
echo ""
