#!/bin/bash
# shellcheck disable=SC2034

# Platform/runtime detection helpers for bootstrap.sh. This file is sourced, not executed.

detect_platform() {
    case "$(uname -s)" in
        Darwin)
            PLATFORM="macos"
            ;;
        Linux)
            PLATFORM="linux"
            # Detect Linux distribution
            if [[ -f /etc/os-release ]]; then
                # /etc/os-release is a runtime-only distro file with no static
                # equivalent shellcheck can follow (-x doesn't help; content is
                # host-specific), so it can't be resolved for analysis.
                # shellcheck disable=SC1091
                . /etc/os-release
                DISTRO="$ID"
            elif [[ -f /etc/debian_version ]]; then
                DISTRO="debian"
            elif [[ -f /etc/redhat-release ]]; then
                DISTRO="rhel"
            fi

            # Detect package manager
            if command -v apt-get &> /dev/null; then
                PKG_MANAGER="apt"
            elif command -v dnf &> /dev/null; then
                PKG_MANAGER="dnf"
            elif command -v yum &> /dev/null; then
                PKG_MANAGER="yum"
            elif command -v pacman &> /dev/null; then
                PKG_MANAGER="pacman"
            elif command -v zypper &> /dev/null; then
                PKG_MANAGER="zypper"
            fi
            ;;
        *)
            PLATFORM="unknown"
            ;;
    esac
}

# Cross-platform browser open
open_url() {
    local url="$1"
    case "$PLATFORM" in
        macos)
            open "$url"
            ;;
        linux)
            if command -v xdg-open &> /dev/null; then
                xdg-open "$url"
            elif command -v gnome-open &> /dev/null; then
                gnome-open "$url"
            elif command -v kde-open &> /dev/null; then
                kde-open "$url"
            else
                print_warning "Could not open browser. Please visit: $url"
                return 1
            fi
            ;;
        *)
            print_warning "Could not open browser. Please visit: $url"
            return 1
            ;;
    esac
}

# Initialize platform state and timeout command detection.
initialize_platform_runtime() {
    detect_platform

    # Detect timeout command (timeout on Linux, gtimeout on macOS via coreutils)
    TIMEOUT_CMD=""
    if command -v timeout &> /dev/null; then
        TIMEOUT_CMD="timeout"
    elif command -v gtimeout &> /dev/null; then
        TIMEOUT_CMD="gtimeout"
    fi
}
