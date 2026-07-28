#!/usr/bin/env bash
# help-coverage: exempt — sourced helper library, not a directly-invoked entry point
#
# apm_domains_lib.sh — the single implementation of "does APM own this deployed
# domain?", sourced by every legacy writer that must stand down for a migrated
# domain (T014/T015, FR-014/FR-027):
#
#   - bootstrap/lib/common.sh   -> deploy_home_skills()
#   - configs/claude/scripts/sync-skills.sh
#
# It lives here rather than in bootstrap/lib/ because sync-skills.sh is a
# standalone CLI installed to ~/.local/bin and cannot source the bootstrap
# libraries. Two copies of this parser would be two chances to disagree about
# who owns a domain, and a disagreement means either two writers (drift) or
# zero (a domain that silently stops updating).
#
# A "domain" is a deployed area with exactly one writer. The registry is
# configs/claude/config/apm_domains.yml.

# apm_owns_domain <name> — 0 if APM owns the domain, 1 otherwise.
#
# Resolution precedence: MANIFEST_APM_DOMAINS (test fixtures) > the repo copy >
# the deployed copy. The registry is read from the REPO first on purpose: an
# ownership marker shipped inside the rsync stream is present after ANY deploy,
# including one that was supposed to be disabled, so it cannot answer "is this
# ours?" (feature 481 learned this the expensive way).
#
# Absent or unreadable registry means "APM owns nothing". The fail-safe
# direction is deliberately the OPPOSITE of the binary-integrity gate: refusing
# to deploy on a missing config would brick bootstrap, whereas installing an
# unverified binary would be a security failure. Fail-closed is not a universal
# rule — it depends on what the failure costs.
apm_owns_domain() {
    local want="$1" registry=""
    if [[ -n "${MANIFEST_APM_DOMAINS:-}" ]]; then
        registry="$MANIFEST_APM_DOMAINS"
    elif [[ -n "${MANIFEST_ROOT:-}" && -f "$MANIFEST_ROOT/configs/claude/config/apm_domains.yml" ]]; then
        registry="$MANIFEST_ROOT/configs/claude/config/apm_domains.yml"
    elif [[ -n "${SCRIPT_DIR:-}" && -f "$SCRIPT_DIR/configs/claude/config/apm_domains.yml" ]]; then
        registry="$SCRIPT_DIR/configs/claude/config/apm_domains.yml"
    elif [[ -f "$HOME/.claude/config/apm_domains.yml" ]]; then
        registry="$HOME/.claude/config/apm_domains.yml"
    fi
    [[ -n "$registry" && -f "$registry" ]] || return 1

    # Accepts both `domains: [a, b]` and a block list under `domains:`.
    awk -v want="$want" '
        /^domains:[[:space:]]*\[/ {
            line = $0
            sub(/^domains:[[:space:]]*\[/, "", line)
            sub(/\].*$/, "", line)
            n = split(line, parts, ",")
            for (i = 1; i <= n; i++) {
                gsub(/[[:space:]"'"'"']/, "", parts[i])
                if (parts[i] == want) { found = 1 }
            }
            next
        }
        /^domains:[[:space:]]*$/ { inlist = 1; next }
        inlist && /^[[:space:]]*-[[:space:]]*/ {
            item = $0
            sub(/^[[:space:]]*-[[:space:]]*/, "", item)
            sub(/[[:space:]]*(#.*)?$/, "", item)
            gsub(/["'"'"']/, "", item)
            if (item == want) { found = 1 }
            next
        }
        inlist && /^[^[:space:]-]/ { inlist = 0 }
        END { exit(found ? 0 : 1) }
    ' "$registry"
}

# The command a contributor should run instead, once a domain is APM-owned.
# Centralised so the skip message and the docs cannot drift apart.
# shellcheck disable=SC2034  # consumed by sourcing scripts (sync-skills.sh, common.sh)
APM_DOMAIN_REPLACEMENT_CMD="apm-dev-sync"

# deploy_domain_selected <name> — should this deploy run touch the domain?
# T011/FR-019: deploy_configs() is monolithic, so without a selector "re-run
# bootstrap for the unmigrated domains only" is not an available action — and
# that action is exactly what FR-019's rollback and T053's un-gate depend on.
#
# MANIFEST_DEPLOY_DOMAINS is a comma-separated allow-list. UNSET OR EMPTY MEANS
# ALL, deliberately: the selector must be inert unless someone asks for it, or
# every existing bootstrap run silently becomes a partial deploy.
deploy_domain_selected() {
    local want="$1" list="${MANIFEST_DEPLOY_DOMAINS:-}" item
    [[ -z "$list" ]] && return 0
    local IFS=,
    for item in $list; do
        # Trim surrounding whitespace so "a, b" behaves like "a,b".
        item="${item#"${item%%[![:space:]]*}"}"
        item="${item%"${item##*[![:space:]]}"}"
        [[ "$item" == "$want" ]] && return 0
    done
    return 1
}
