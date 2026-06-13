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

    case "$hook" in
        after_config_load)
            BOOTSTRAP_HOOKS_AFTER_CONFIG_LOAD+=("$func")
            ;;
        before_install)
            BOOTSTRAP_HOOKS_BEFORE_INSTALL+=("$func")
            ;;
        after_deploy)
            BOOTSTRAP_HOOKS_AFTER_DEPLOY+=("$func")
            ;;
        after_auth)
            BOOTSTRAP_HOOKS_AFTER_AUTH+=("$func")
            ;;
        after_verify)
            BOOTSTRAP_HOOKS_AFTER_VERIFY+=("$func")
            ;;
        *)
            print_warning "Unknown bootstrap hook '$hook' (function: $func)"
            return 1
            ;;
    esac
}

run_bootstrap_hook() {
    local hook="$1"
    local func

    case "$hook" in
        after_config_load)
            for func in ${BOOTSTRAP_HOOKS_AFTER_CONFIG_LOAD[@]+"${BOOTSTRAP_HOOKS_AFTER_CONFIG_LOAD[@]}"}; do
                if declare -F "$func" > /dev/null; then
                    print_step "Running module hook ($hook): $func"
                    "$func"
                else
                    print_warning "Registered hook function not found: $func"
                fi
            done
            ;;
        before_install)
            for func in ${BOOTSTRAP_HOOKS_BEFORE_INSTALL[@]+"${BOOTSTRAP_HOOKS_BEFORE_INSTALL[@]}"}; do
                if declare -F "$func" > /dev/null; then
                    print_step "Running module hook ($hook): $func"
                    "$func"
                else
                    print_warning "Registered hook function not found: $func"
                fi
            done
            ;;
        after_deploy)
            for func in ${BOOTSTRAP_HOOKS_AFTER_DEPLOY[@]+"${BOOTSTRAP_HOOKS_AFTER_DEPLOY[@]}"}; do
                if declare -F "$func" > /dev/null; then
                    print_step "Running module hook ($hook): $func"
                    "$func"
                else
                    print_warning "Registered hook function not found: $func"
                fi
            done
            ;;
        after_auth)
            for func in ${BOOTSTRAP_HOOKS_AFTER_AUTH[@]+"${BOOTSTRAP_HOOKS_AFTER_AUTH[@]}"}; do
                if declare -F "$func" > /dev/null; then
                    print_step "Running module hook ($hook): $func"
                    "$func"
                else
                    print_warning "Registered hook function not found: $func"
                fi
            done
            ;;
        after_verify)
            for func in ${BOOTSTRAP_HOOKS_AFTER_VERIFY[@]+"${BOOTSTRAP_HOOKS_AFTER_VERIFY[@]}"}; do
                if declare -F "$func" > /dev/null; then
                    print_step "Running module hook ($hook): $func"
                    "$func"
                else
                    print_warning "Registered hook function not found: $func"
                fi
            done
            ;;
        *)
            print_warning "Attempted to run unknown bootstrap hook '$hook'"
            return 1
            ;;
    esac
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
