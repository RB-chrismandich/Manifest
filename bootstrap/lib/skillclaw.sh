#!/usr/bin/env bash
# skillclaw.sh - Manage SkillClaw transcript-evolution state.
#
# Responsibilities:
#   - chmod 700 the capture storage (secrets honeypot — Tier 1).
#   - Remove any legacy proxy wrapper block left by a prior install.
#   - Remove retired launchd/systemd supervisor units.
#
# The proxy/daemon model has been retired. SkillClaw now uses transcript-fed
# evolution: enabling = storage-only setup, no daemon, no proxy, no wrappers.
#
# Sourced by bootstrap.sh. bash 3.2-compatible.

# Storage root is overridable for tests.
SKILLCLAW_HOME="${SKILLCLAW_HOME:-$HOME/.skillclaw}"

SKILLCLAW_WRAP_BEGIN="# >>> MANIFEST SKILLCLAW WRAPPERS >>>"
SKILLCLAW_WRAP_END="# <<< MANIFEST SKILLCLAW WRAPPERS <<<"

# Remove any existing managed wrapper block from a profile file (idempotent).
# Kept to strip legacy claude()/codex() blocks from prior proxy-based installs.
skillclaw_remove_wrappers() {
    local profile="$1"
    [[ -f "$profile" ]] || return 0
    # Delete the inclusive marker block.
    sed -e "/$SKILLCLAW_WRAP_BEGIN/,/$SKILLCLAW_WRAP_END/d" "$profile" > "${profile}.tmp" \
        && mv "${profile}.tmp" "$profile"
}

# Remove the retired launchd/systemd supervisor if a prior install left one.
_skillclaw_remove_launchd() {
    case "$(uname -s)" in
        Darwin)
            local plist="$HOME/Library/LaunchAgents/com.manifest.skillclaw.plist"
            [[ -f "$plist" ]] && { launchctl unload "$plist" >/dev/null 2>&1 || true; rm -f "$plist"; }
            ;;
        Linux)
            local unit="$HOME/.config/systemd/user/skillclaw.service"
            [[ -f "$unit" ]] && { systemctl --user disable --now skillclaw.service >/dev/null 2>&1 || true; rm -f "$unit"; }
            ;;
    esac
}

# Apply desired state. Transcript-fed evolution needs NO daemon and NO proxy —
# enabling just ensures storage exists and any legacy proxy wrappers are removed.
skillclaw_apply_state() {
    local profile="${SHELL_PROFILE_FILE:-$HOME/.zshrc}"
    # Always strip any legacy proxy wrapper block (full teardown of the old model).
    skillclaw_remove_wrappers "$profile"
    _skillclaw_remove_launchd
    if [[ "${ENABLE_SKILLCLAW:-false}" == true ]]; then
        mkdir -p "$SKILLCLAW_HOME/sessions" "$SKILLCLAW_HOME/skills"
        chmod 700 "$SKILLCLAW_HOME" 2>/dev/null || true
        print_success "SkillClaw enabled (transcript evolution; no daemon, no proxy)"
    else
        print_info "SkillClaw disabled (storage left intact; nothing running)"
    fi
}
