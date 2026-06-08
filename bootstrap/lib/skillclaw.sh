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
    port=$(python3 - "$cfg" <<'PY'
import sys, yaml
print(yaml.safe_load(open(sys.argv[1]))["proxy"]["port"])
PY
)
    storage=$(python3 - "$cfg" <<'PY'
import sys, os, yaml
print(os.path.expanduser(yaml.safe_load(open(sys.argv[1]))["storage"]["root"]))
PY
)
    if command -v skillclaw >/dev/null 2>&1; then
        skillclaw setup --non-interactive --port "$port" --storage "$storage" \
            || print_warning "skillclaw setup returned non-zero (continuing)"
    fi
    print_success "SkillClaw configured (port $port, storage $storage)"
}

SKILLCLAW_WRAP_BEGIN="# >>> MANIFEST SKILLCLAW WRAPPERS >>>"
SKILLCLAW_WRAP_END="# <<< MANIFEST SKILLCLAW WRAPPERS <<<"

# Remove any existing managed wrapper block from a profile file (idempotent).
skillclaw_remove_wrappers() {
    local profile="$1"
    [[ -f "$profile" ]] || return 0
    # Delete the inclusive marker block.
    sed -e "/$SKILLCLAW_WRAP_BEGIN/,/$SKILLCLAW_WRAP_END/d" "$profile" > "${profile}.tmp" \
        && mv "${profile}.tmp" "$profile"
}

# Write the fail-open runtime wrapper block. The health probe runs at INVOCATION
# time (not shell init), capped at 0.3s, and degrades to direct-to-provider.
skillclaw_write_wrappers() {
    local profile="$1"
    mkdir -p "$(dirname "$profile")"
    touch "$profile"
    skillclaw_remove_wrappers "$profile"
    cat >> "$profile" << EOF
$SKILLCLAW_WRAP_BEGIN
# Managed by bootstrap/lib/skillclaw.sh — do not edit between these markers.
export SKILLCLAW_PORT="\${SKILLCLAW_PORT:-$SKILLCLAW_PORT}"
_skillclaw_up() {
    curl -sf --max-time 0.3 "http://127.0.0.1:\${SKILLCLAW_PORT}/health" >/dev/null 2>&1
}
_skillclaw_run() {
    # \$1=env var name, \$2=base url, rest=command
    local var="\$1" url="\$2"; shift 2
    if [ -z "\${SKILLCLAW_BYPASS:-}" ] && _skillclaw_up; then
        env "\$var=\$url" "\$@"
    else
        "\$@"
    fi
}
claude() { _skillclaw_run ANTHROPIC_BASE_URL "http://127.0.0.1:\${SKILLCLAW_PORT}" command claude "\$@"; }
codex()  { _skillclaw_run OPENAI_BASE_URL    "http://127.0.0.1:\${SKILLCLAW_PORT}/v1" command codex "\$@"; }
$SKILLCLAW_WRAP_END
EOF
}
