#!/usr/bin/env bash
# skillclaw.sh - Install, configure, and manage the SkillClaw capture proxy.
#
# Responsibilities:
#   - Install SkillClaw (pip) when enabled.
#   - chmod 700 the capture storage (secrets honeypot — Tier 1).
#   - Non-interactive `skillclaw setup` from configs/claude/config/skillclaw.yml.
#   - Write/remove fail-open runtime wrapper functions (see skillclaw_wrappers).
#   - Daemon lifecycle + crash supervisor (see skillclaw_daemon).
#
# Sourced by bootstrap.sh. bash 3.2-compatible.

# Storage root is overridable for tests.
SKILLCLAW_HOME="${SKILLCLAW_HOME:-$HOME/.skillclaw}"
SKILLCLAW_PORT="${SKILLCLAW_PORT:-8765}"

# Create capture storage with locked-down perms. Secrets may transit here.
skillclaw_init_storage() {
    print_step "Preparing SkillClaw storage at $SKILLCLAW_HOME..."
    mkdir -p "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
    chmod 700 "$SKILLCLAW_HOME" "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
    print_success "SkillClaw storage ready (700)"
}

# Install SkillClaw via pip if missing.
install_skillclaw() {
    if [[ "${ENABLE_SKILLCLAW:-false}" != true ]]; then
        return 0
    fi
    if command -v skillclaw >/dev/null 2>&1; then
        print_info "SkillClaw already installed"
        return 0
    fi
    print_step "Installing SkillClaw..."
    if command -v pipx >/dev/null 2>&1; then
        pipx install skillclaw || { print_error "pipx install skillclaw failed"; return 1; }
    elif command -v pip3 >/dev/null 2>&1; then
        pip3 install --user skillclaw || { print_error "pip3 install skillclaw failed"; return 1; }
    else
        print_error "Neither pipx nor pip3 found; cannot install SkillClaw"
        return 1
    fi
    print_success "SkillClaw installed"
}

# Non-interactive setup from skillclaw.yml. Idempotent.
configure_skillclaw() {
    if [[ "${ENABLE_SKILLCLAW:-false}" != true ]]; then
        return 0
    fi
    skillclaw_init_storage
    local cfg="${SKILLCLAW_CONFIG:-$HOME/.claude/config/skillclaw.yml}"
    if [[ ! -f "$cfg" ]]; then
        print_warning "skillclaw.yml not found at $cfg; skipping setup"
        return 0
    fi
    print_step "Configuring SkillClaw (non-interactive)..."
    # `skillclaw setup` reads provider/model/storage flags; values come from skillclaw.yml.
    local port storage
    port=$(python3 -c "import yaml; print(yaml.safe_load(open('$cfg'))['proxy']['port'])")
    storage=$(python3 -c "import yaml,os; print(os.path.expanduser(yaml.safe_load(open('$cfg'))['storage']['root']))")
    if command -v skillclaw >/dev/null 2>&1; then
        skillclaw setup --non-interactive --port "$port" --storage "$storage" \
            || print_warning "skillclaw setup returned non-zero (continuing)"
    fi
    print_success "SkillClaw configured (port $port, storage $storage)"
}
