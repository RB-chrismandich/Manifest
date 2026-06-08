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

SKILLCLAW_PIDFILE="${SKILLCLAW_PIDFILE:-$SKILLCLAW_HOME/skillclaw.pid}"

# start|stop|status for the capture daemon. Capture is lossy-by-design; a dead
# daemon must never block agents (the wrappers already fail open).
skillclaw_daemon() {
    local action="${1:-status}"
    case "$action" in
        start)
            command -v skillclaw >/dev/null 2>&1 || { print_error "skillclaw not installed"; return 1; }
            skillclaw start --daemon --port "$SKILLCLAW_PORT" || return 1
            print_success "SkillClaw daemon started on $SKILLCLAW_PORT"
            ;;
        stop)
            skillclaw stop >/dev/null 2>&1 || true
            print_info "SkillClaw daemon stopped"
            ;;
        status)
            if [[ -f "$SKILLCLAW_PIDFILE" ]] && kill -0 "$(cat "$SKILLCLAW_PIDFILE")" 2>/dev/null; then
                echo "running"
                return 0
            fi
            echo "stopped"
            return 1
            ;;
        *)
            print_error "usage: skillclaw_daemon start|stop|status"
            return 2
            ;;
    esac
}

# Emit a platform supervisor unit so a crashed daemon auto-restarts (§5.3).
# $1 = platform (darwin|linux), $2 = output path.
skillclaw_supervisor_unit() {
    local platform="$1" out="$2"
    local bin; bin="$(command -v skillclaw 2>/dev/null || echo skillclaw)"
    mkdir -p "$(dirname "$out")"
    case "$platform" in
        darwin)
            cat > "$out" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.manifest.skillclaw</string>
  <key>ProgramArguments</key>
  <array>
    <string>$bin</string><string>start</string><string>--port</string><string>$SKILLCLAW_PORT</string>
  </array>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
            ;;
        linux)
            cat > "$out" << EOF
[Unit]
Description=SkillClaw capture proxy
[Service]
ExecStart=$bin start --port $SKILLCLAW_PORT
Restart=on-failure
[Install]
WantedBy=default.target
EOF
            ;;
        *)
            print_error "unknown platform: $platform"
            return 1
            ;;
    esac
}

# Install + load the supervisor for the current platform (best-effort).
skillclaw_install_supervisor() {
    case "$(uname -s)" in
        Darwin)
            local plist="$HOME/Library/LaunchAgents/com.manifest.skillclaw.plist"
            skillclaw_supervisor_unit darwin "$plist"
            launchctl unload "$plist" >/dev/null 2>&1 || true
            launchctl load "$plist" >/dev/null 2>&1 || print_warning "launchctl load failed (continuing)"
            ;;
        Linux)
            local unit="$HOME/.config/systemd/user/skillclaw.service"
            skillclaw_supervisor_unit linux "$unit"
            systemctl --user daemon-reload >/dev/null 2>&1 || true
            systemctl --user enable --now skillclaw.service >/dev/null 2>&1 \
                || print_warning "systemctl enable failed (continuing)"
            ;;
    esac
}

# Apply the desired state based on ENABLE_SKILLCLAW. Called from bootstrap main.
# Writes wrappers to SHELL_PROFILE_FILE (set by configure_shell_profile_state).
skillclaw_apply_state() {
    local profile="${SHELL_PROFILE_FILE:-$HOME/.zshrc}"
    if [[ "${ENABLE_SKILLCLAW:-false}" == true ]]; then
        configure_skillclaw
        skillclaw_write_wrappers "$profile"
        skillclaw_install_supervisor
        skillclaw_daemon start || print_warning "Could not start SkillClaw daemon (wrappers fail open)"
        print_success "SkillClaw enabled (capture via $profile)"
    else
        skillclaw_remove_wrappers "$profile"
        skillclaw_daemon stop || true
        print_info "SkillClaw disabled (wrappers removed)"
    fi
}
