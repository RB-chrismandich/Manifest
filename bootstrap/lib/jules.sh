#!/bin/bash
# Opt-in Jules installation/authentication. Sourced by bootstrap.sh.

check_jules() {
    if [[ "${ENABLE_JULES:-false}" != true ]]; then
        return 0
    fi
    if command_exists jules; then
        print_success "Jules CLI is installed"
        return 0
    fi
    if ! command_exists npm; then
        print_error "Jules requires npm: install Node.js, then npm install -g @google/jules@0.1.42"
        return 1
    fi
    if prompt_yes_no "Install Jules CLI (npm @google/jules@0.1.42)?"; then
        if npm install -g @google/jules@0.1.42 && command_exists jules; then
            print_success "Jules CLI installed"
            return 0
        fi
    fi
    print_error "Jules CLI is not installed; use --disable-jules to opt out"
    return 1
}

check_jules_auth() {
    if [[ "${ENABLE_JULES:-false}" != true ]]; then
        return 0
    fi
    if ! command_exists jules || ! command_exists python3; then
        print_error "Jules authentication check requires jules and python3"
        return 1
    fi
    local probe="$SCRIPT_DIR/plugins/manifest-delegate/manifest_delegate/jules_cli.py"
    if python3 "$probe" --auth; then
        print_success "Jules is authenticated with repository access"
        return 0
    fi
    # --force must never open a browser or hang on OAuth in unattended setup.
    if [[ -t 0 && "${FORCE:-false}" != true ]] && prompt_yes_no "Authenticate Jules with browser OAuth now?"; then
        if jules login && python3 "$probe" --auth; then
            print_success "Jules is authenticated with repository access"
            return 0
        fi
    fi
    print_error "Jules access is unverified. Run jules login; authorize the GitHub App for your repo."
    return 1
}
