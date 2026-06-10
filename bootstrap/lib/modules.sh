#!/bin/bash

# Extensibility hooks for bootstrap.sh. Modules can register functions
# against lifecycle hook names.

# shellcheck disable=SC2034
declare -a BOOTSTRAP_HOOKS_AFTER_CONFIG_LOAD=()
# shellcheck disable=SC2034
declare -a BOOTSTRAP_HOOKS_BEFORE_INSTALL=()
# shellcheck disable=SC2034
declare -a BOOTSTRAP_HOOKS_AFTER_DEPLOY=()
# shellcheck disable=SC2034
declare -a BOOTSTRAP_HOOKS_AFTER_AUTH=()
# shellcheck disable=SC2034
declare -a BOOTSTRAP_HOOKS_AFTER_VERIFY=()

register_bootstrap_hook() {
    local hook="$1"
    local func="$2"
    local var_name=""

    case "$hook" in
        after_config_load)
            var_name="BOOTSTRAP_HOOKS_AFTER_CONFIG_LOAD"
            ;;
        before_install)
            var_name="BOOTSTRAP_HOOKS_BEFORE_INSTALL"
            ;;
        after_deploy)
            var_name="BOOTSTRAP_HOOKS_AFTER_DEPLOY"
            ;;
        after_auth)
            var_name="BOOTSTRAP_HOOKS_AFTER_AUTH"
            ;;
        after_verify)
            var_name="BOOTSTRAP_HOOKS_AFTER_VERIFY"
            ;;
        *)
            print_warning "Unknown bootstrap hook '$hook' (function: $func)"
            return 1
            ;;
    esac

    eval "$var_name+=(\"$func\")"
}

run_bootstrap_hook() {
    local hook="$1"
    local var_name=""
    local funcs=()
    local func

    case "$hook" in
        after_config_load)
            var_name="BOOTSTRAP_HOOKS_AFTER_CONFIG_LOAD"
            ;;
        before_install)
            var_name="BOOTSTRAP_HOOKS_BEFORE_INSTALL"
            ;;
        after_deploy)
            var_name="BOOTSTRAP_HOOKS_AFTER_DEPLOY"
            ;;
        after_auth)
            var_name="BOOTSTRAP_HOOKS_AFTER_AUTH"
            ;;
        after_verify)
            var_name="BOOTSTRAP_HOOKS_AFTER_VERIFY"
            ;;
        *)
            print_warning "Attempted to run unknown bootstrap hook '$hook'"
            return 1
            ;;
    esac

    # Guard inside the eval too: an EMPTY hook array would crash here under
    # Bash 3.2 + set -u before the guarded loop below is ever reached.
    eval "funcs=(\${${var_name}[@]+\"\${${var_name}[@]}\"})"
    for func in ${funcs[@]+"${funcs[@]}"}; do
        if declare -F "$func" > /dev/null; then
            print_step "Running module hook ($hook): $func"
            "$func"
        else
            print_warning "Registered hook function not found: $func"
        fi
    done
}

load_bootstrap_modules() {
    local module_dir="${BOOTSTRAP_MODULE_DIR:-$SCRIPT_DIR/bootstrap/modules}"
    local module
    local loaded=0

    if [[ ! -d "$module_dir" ]]; then
        return 0
    fi

    while IFS= read -r module; do
        # shellcheck disable=SC1090
        source "$module"
        loaded=$((loaded + 1))
        print_info "Loaded bootstrap module: ${module##*/}"
    done < <(find "$module_dir" -maxdepth 1 -type f -name "*.sh" | sort)

    if [[ $loaded -gt 0 ]]; then
        print_success "Bootstrap modules loaded: $loaded"
    fi
}
