#!/bin/bash

# Install and platform helpers for bootstrap.sh. This file is sourced, not executed.

check_platform() {
    case "$PLATFORM" in
        macos)
            print_success "Running on macOS $(sw_vers -productVersion)"
            ;;
        linux)
            local version=""
            if [[ -f /etc/os-release ]]; then
                # /etc/os-release is a runtime-only distro file with no static
                # equivalent shellcheck can follow; content is host-specific.
                # shellcheck disable=SC1091
                . /etc/os-release
                version="$PRETTY_NAME"
            else
                version="$(uname -r)"
            fi
            print_success "Running on Linux: $version"
            if [[ -n "$PKG_MANAGER" ]]; then
                print_info "Package manager: $PKG_MANAGER"
            else
                print_warning "No supported package manager detected"
            fi
            ;;
        *)
            print_error "Unsupported platform: $(uname -s)"
            print_info "This script supports macOS and Linux"
            exit 1
            ;;
    esac
}

# Check and install Homebrew (macOS) or ensure package manager is available (Linux)
install_package_manager() {
    if [[ "$PLATFORM" == "macos" ]]; then
        print_step "Checking for Homebrew..."

        if command_exists brew; then
            print_success "Homebrew is installed"
            print_step "Updating Homebrew..."
            brew update --quiet
        else
            print_warning "Homebrew not found"
            if prompt_yes_no "Install Homebrew?"; then
                print_step "Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

                # Add Homebrew to PATH for Apple Silicon
                if [[ -f "/opt/homebrew/bin/brew" ]]; then
                    # shellcheck disable=SC1090
                    source <(/opt/homebrew/bin/brew shellenv)
                fi
                # Add Homebrew to PATH for Intel Mac
                if [[ -f "/usr/local/bin/brew" ]]; then
                    # shellcheck disable=SC1090
                    source <(/usr/local/bin/brew shellenv)
                fi
                print_success "Homebrew installed"
            else
                print_warning "Homebrew not installed - some installations may fail"
            fi
        fi
    elif [[ "$PLATFORM" == "linux" ]]; then
        print_step "Checking package manager..."

        if [[ -z "$PKG_MANAGER" ]]; then
            print_warning "No supported package manager found"
            print_info "Supported: apt, dnf, yum, pacman, zypper"
            print_info "You may need to install dependencies manually"
        else
            print_success "Package manager available: $PKG_MANAGER"

            # Update package lists
            case "$PKG_MANAGER" in
                apt)
                    if prompt_yes_no "Update apt package lists?"; then
                        print_step "Updating package lists..."
                        sudo apt-get update -qq
                    fi
                    ;;
                dnf | yum)
                    # dnf/yum auto-updates metadata
                    ;;
                pacman)
                    if prompt_yes_no "Sync pacman database?"; then
                        print_step "Syncing database..."
                        sudo pacman -Sy --noconfirm
                    fi
                    ;;
            esac
        fi
    fi
}

# shellcheck source=bootstrap/lib/prerequisites.sh
source "$(dirname "${BASH_SOURCE[0]}")/prerequisites.sh"

# shellcheck source=bootstrap/lib/cli_installers.sh
source "$(dirname "${BASH_SOURCE[0]}")/cli_installers.sh"

# shellcheck source=bootstrap/lib/optional_cli.sh
source "$(dirname "${BASH_SOURCE[0]}")/optional_cli.sh"

# Read the optional smoke and browser-use toggles out of deployed services.yml
# in one probe. Echoes "<smoke> <browser_use>" as 0/1 flags; returns non-zero
# when the file cannot be parsed as the expected services mapping.
#
# The home venv is preferred because it normally has PyYAML. Before its first
# sync, though, the host interpreter can lack that dependency (or, in an
# isolated home, its user site). The awk fallback below reads only the two
# fixed service toggles so a requested optional group is never silently lost.
read_service_group_flags() {
    local services_yml="$1" target_dir="$2"
    local py
    # The runtime's own interpreter first: it always has PyYAML once synced, so a
    # host python3 without PyYAML stops mattering after the first bootstrap.
    for py in "$target_dir/.venv/bin/python3" "$target_dir/.venv/bin/python" python3; do
        if [[ "$py" == python3 ]]; then
            command_exists python3 || continue
        else
            [[ -x "$py" ]] || continue
        fi
        "$py" - "$services_yml" << 'PY' 2> /dev/null && return 0
import sys

try:
    import yaml
except ImportError:
    sys.exit(2)

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
except (OSError, yaml.YAMLError):
    sys.exit(3)

services = data.get("services") if isinstance(data, dict) else None
services = services if isinstance(services, dict) else {}


def on(name: str) -> str:
    svc = services.get(name)
    return "1" if isinstance(svc, dict) and svc.get("enabled") else "0"


print(on("smoke"), on("browser_use"))
PY
    done
    awk '
        /^services:[[:space:]]*$/ { services=1; next }
        services && /^  (smoke|browser_use):[[:space:]]*$/ { name=$1; sub(":", "", name); next }
        services && /^  [A-Za-z_][A-Za-z0-9_]*:[[:space:]]*$/ { name=""; next }
        services && /^    enabled:[[:space:]]*(true|false)[[:space:]]*$/ {
            value=$2 == "true" ? 1 : 0
            if (name == "smoke") smoke=value
            if (name == "browser_use") browser=value
        }
        END {
            if (!services) exit 1
            print smoke+0, browser+0
        }
    ' "$services_yml"
}

# Recreate a venv whose interpreter no longer works. A Python upgrade (or a tree
# copied from another home) leaves the directory populated but every console
# script pointing at a dead absolute path, and `uv sync` then fails in ways that
# read like a lockfile problem.
heal_broken_home_venv() {
    local venv="$1"
    [[ "$venv" == */.venv ]] || return 0
    [[ -d "$venv" ]] || return 0
    local py
    for py in "$venv/bin/python3" "$venv/bin/python"; do
        if [[ -x "$py" ]] && "$py" -c "" 2> /dev/null; then
            return 0
        fi
    done
    print_warning "Home venv interpreter is unusable — recreating $venv"
    rm -rf "$venv"
}

# Install ~/.local/bin/manifest defensively. Everything here answers a way the
# destination can already be occupied: by our own current copy (nothing to do),
# by a stale copy (replace), by a symlink (never write THROUGH it — that silently
# overwrites whatever it points at), by another tool's `manifest` (back it up
# rather than clobber), or by a directory (refuse and say so).
install_manifest_wrapper() {
    local src="$SCRIPT_DIR/configs/claude/scripts/manifest-cli.sh"
    local bin_dir="$HOME/.local/bin" dest="$HOME/.local/bin/manifest"

    if [[ ! -f "$src" ]]; then
        print_error "manifest wrapper source is missing ($src) — incomplete checkout?"
        return 1
    fi
    if ! mkdir -p "$bin_dir" 2> /dev/null; then
        print_error "Cannot create $bin_dir — manifest CLI not installed"
        return 1
    fi
    if [[ ! -w "$bin_dir" ]]; then
        print_error "$bin_dir is not writable — manifest CLI not installed"
        return 1
    fi
    if [[ -d "$dest" && ! -L "$dest" ]]; then
        print_error "$dest is a directory — remove it, then re-run ./bootstrap.sh"
        return 1
    fi

    # A bootstrap killed mid-install leaves manifest.tmp.<pid> behind; ~/.local/bin
    # is on PATH, so that litter is a stale executable sitting next to the wrapper.
    rm -f "$bin_dir"/manifest.tmp.* 2> /dev/null || true

    if [[ -L "$dest" ]]; then
        local link_target
        link_target="$(readlink "$dest" 2> /dev/null)" || link_target="?"
        print_warning "Replacing symlink $dest -> $link_target with a managed copy"
        rm -f "$dest" || {
            print_error "Could not remove symlink $dest"
            return 1
        }
    elif [[ -f "$dest" ]] && ! grep -q 'manifest-cli-wrapper' "$dest" 2> /dev/null; then
        # Not ours: a same-named CLI from another project, or a hand-written script.
        local backup="$dest.pre-manifest.bak"
        if [[ -e "$backup" ]]; then
            print_warning "$dest is not Manifest's wrapper; existing backup kept at $backup"
        else
            print_warning "$dest was not installed by Manifest — backing it up to $backup"
            cp -p "$dest" "$backup" 2> /dev/null || print_warning "Could not back up $dest"
        fi
    fi

    if cmp -s "$src" "$dest" 2> /dev/null; then
        # Already installed and byte-identical: heal a lost +x bit and stop.
        [[ -x "$dest" ]] || chmod +x "$dest" 2> /dev/null || true
        print_info "manifest CLI already current at $dest"
        return 0
    fi

    # Write to a sibling temp file and rename: an interrupted or short copy must
    # never become the wrapper every skill and hook invokes.
    local tmp="$dest.tmp.$$"
    if ! cp "$src" "$tmp" 2> /dev/null; then
        rm -f "$tmp"
        print_error "Could not write $tmp — manifest CLI not installed"
        return 1
    fi
    if ! chmod +x "$tmp" || ! mv -f "$tmp" "$dest"; then
        rm -f "$tmp"
        print_error "Could not install $dest — manifest CLI not installed"
        return 1
    fi
    # Verify what landed instead of trusting cp's exit status (full disk, quota).
    if ! cmp -s "$src" "$dest" || [[ ! -x "$dest" ]]; then
        print_error "$dest did not verify after install — re-run ./bootstrap.sh"
        return 1
    fi
    print_success "manifest CLI installed at $dest"
    return 0
}

# Record install provenance outside ~/.claude so it survives that tree being
# deleted — which is exactly when the wrapper needs to name the clone to re-run.
write_runtime_stamp() {
    local target_dir="$1" groups="$2"
    local state_root="${MANIFEST_STATE_ROOT:-$HOME/.manifest}"
    mkdir -p "$state_root" 2> /dev/null || return 0
    local tmp="$state_root/runtime.env.tmp.$$"
    {
        echo "clone_path=$SCRIPT_DIR"
        echo "runtime_root=$target_dir"
        echo "groups=$groups"
        echo "wrapper=$HOME/.local/bin/manifest"
        echo "synced_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$tmp" 2> /dev/null || {
        rm -f "$tmp"
        return 0
    }
    mv -f "$tmp" "$state_root/runtime.env" 2> /dev/null || rm -f "$tmp"
    return 0
}

# Sync the home Python runtime via uv (replaces pip install --user).
# Reads deployed services.yml for optional dependency groups, runs uv sync, optionally
# installs Playwright Chromium for smoke, and deploys ~/.local/bin/manifest wrapper.
#
# Fail-open by design: every failure below warns and returns 0 so one broken
# runtime cannot abort a bootstrap that still has assistants to configure. The
# runtime's own `manifest doctor` and env-check are the fail-closed gates.
uv_sync_home_runtime() {
    local target_dir="${TARGET_DIR:-$HOME/.claude}"
    local uv_bin="${MANIFEST_VERIFIED_UV_BIN:-}"
    if [[ -z "$uv_bin" || ! -x "$uv_bin" ]]; then
        print_warning "verified uv was not established in this bootstrap invocation — skipping home runtime sync"
        return 0
    fi

    # uv sync needs both deploy artifacts. Without this check the failure surfaces
    # as a raw uv error about a missing project, blaming the wrong thing.
    local artifact
    for artifact in pyproject.toml uv.lock; do
        if [[ ! -f "$target_dir/$artifact" ]]; then
            print_error "$target_dir/$artifact is missing — deploy is incomplete, skipping home runtime sync"
            return 0
        fi
    done

    local -a group_flags=()
    local install_playwright=false
    local groups_csv="core"
    local services_yml="$target_dir/config/services.yml"
    local flags="" smoke_on=0 browser_on=0

    if [[ ! -f "$services_yml" ]]; then
        print_warning "$services_yml not found — syncing core runtime only (no optional groups)"
    elif flags="$(read_service_group_flags "$services_yml" "$target_dir")"; then
        read -r smoke_on browser_on <<< "$flags" || true
    else
        # No interpreter could parse services.yml. Preserving the previous sync's
        # group selection beats silently downgrading an enabled service to core.
        local prev_groups=""
        prev_groups="$(sed -n 's/^groups=//p' "${MANIFEST_STATE_ROOT:-$HOME/.manifest}/runtime.env" 2> /dev/null | tail -n 1)" || prev_groups=""
        print_warning "Could not read $services_yml (unreadable, not valid YAML, or no interpreter with PyYAML) — optional groups unresolved"
        case "$prev_groups" in
            *smoke-agent*) browser_on=1 ;;
        esac
        case "$prev_groups" in
            *smoke*) smoke_on=1 ;;
        esac
        if [[ -n "$prev_groups" && "$prev_groups" != "core" ]]; then
            print_warning "Reusing the previous sync's groups ($prev_groups) from the runtime stamp"
        fi
    fi

    # browser-use implies smoke (its deps layer on top), so fold the two toggles
    # into one group list. Deduplicated because groups_csv is recorded in the
    # runtime stamp and read back by the unresolved-services path above.
    if [[ "$browser_on" == 1 ]]; then
        smoke_on=1
    fi
    if [[ "$smoke_on" == 1 ]]; then
        group_flags+=(--group smoke)
        install_playwright=true
        groups_csv="$groups_csv,smoke"
    fi
    if [[ "$browser_on" == 1 ]]; then
        group_flags+=(--group smoke-agent)
        groups_csv="$groups_csv,smoke-agent"
    fi

    heal_broken_home_venv "$target_dir/.venv"

    print_step "Syncing home Python runtime (uv)..."
    if ! "$uv_bin" sync --project "$target_dir" "${group_flags[@]+"${group_flags[@]}"}"; then
        print_warning "uv sync failed — home runtime may be unavailable"
        if [[ -x "$HOME/.local/bin/manifest" ]]; then
            print_warning "Existing manifest CLI kept, but its runtime may be stale — fix uv and re-run ./bootstrap.sh"
        fi
        return 0
    fi

    # uv can exit 0 with a venv that lacks the console script (e.g. a pyproject
    # that stopped declaring the package). Warn, but still install the wrapper:
    # its runtime check names this state precisely, which beats `command not found`.
    if [[ ! -e "$target_dir/.venv/bin/manifest" ]]; then
        print_warning "uv sync completed but $target_dir/.venv/bin/manifest is missing — check $target_dir/pyproject.toml"
    fi

    if [[ "$install_playwright" == true ]]; then
        if [[ -x "$target_dir/.venv/bin/playwright" ]]; then
            "$target_dir/.venv/bin/playwright" install chromium || print_warning "playwright install chromium failed"
        else
            print_warning "smoke is enabled but $target_dir/.venv/bin/playwright is missing — skipping browser install"
        fi
    fi

    ensure_local_bin_on_path
    install_manifest_wrapper || true
    write_runtime_stamp "$target_dir" "$groups_csv"
    print_success "Home runtime synced (groups: $groups_csv)"
}
