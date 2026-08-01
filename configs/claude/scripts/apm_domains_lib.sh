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
# _apm_registry_path — the ownership registry this machine should consult, or
# empty. Resolution order is unchanged; it is factored out so the two state
# readers below cannot drift apart on WHERE they look.
_apm_registry_path() {
    if [[ -n "${MANIFEST_APM_DOMAINS:-}" ]]; then
        printf '%s' "$MANIFEST_APM_DOMAINS"
    elif [[ -n "${MANIFEST_ROOT:-}" && -f "$MANIFEST_ROOT/configs/claude/config/apm_domains.yml" ]]; then
        printf '%s' "$MANIFEST_ROOT/configs/claude/config/apm_domains.yml"
    elif [[ -n "${SCRIPT_DIR:-}" && -f "$SCRIPT_DIR/configs/claude/config/apm_domains.yml" ]]; then
        printf '%s' "$SCRIPT_DIR/configs/claude/config/apm_domains.yml"
    elif [[ -f "$HOME/.claude/config/apm_domains.yml" ]]; then
        printf '%s' "$HOME/.claude/config/apm_domains.yml"
    fi
}

# _apm_key_lists <key> <want> — 0 if <want> appears under top-level <key>.
#
# Parameterised rather than copied: `domains:` and `retired:` must agree on what
# counts as membership, and a second hand-maintained parser is exactly how the
# two states start disagreeing about the same file. Accepts both the flow form
# (`key: [a, b]`) and a block list. The list ends at the next unindented key, so
# adding a third state later needs no change here.
_apm_key_lists() {
    local key="$1" want="$2" registry
    registry="$(_apm_registry_path)"
    [[ -n "$registry" && -f "$registry" ]] || return 1

    awk -v want="$want" -v key="$key" '
        $0 ~ "^" key ":[ \t]*\\[" {
            line = $0
            sub("^" key ":[ \t]*\\[", "", line)
            sub(/\].*$/, "", line)
            n = split(line, parts, ",")
            for (i = 1; i <= n; i++) {
                gsub(/[ \t"'"'"']/, "", parts[i])
                if (parts[i] == want) { found = 1 }
            }
            next
        }
        $0 ~ "^" key ":[ \t]*$" { inlist = 1; next }
        inlist && /^[ \t]*-[ \t]*/ {
            item = $0
            sub(/^[ \t]*-[ \t]*/, "", item)
            sub(/[ \t]*(#.*)?$/, "", item)
            gsub(/["'"'"']/, "", item)
            if (item == want) { found = 1 }
            next
        }
        inlist && /^[^ \t-]/ { inlist = 0 }
        END { exit(found ? 0 : 1) }
    ' "$registry"
}

# apm_owns_domain <name> — 0 if APM owns the domain, 1 otherwise.
apm_owns_domain() {
    _apm_key_lists domains "$1"
}

# domain_retired <name> — 0 if the domain is owned by NEITHER pipeline.
#
# The registry was strictly two-state: listed meant APM writes, and UNLISTED
# MEANT THE LEGACY WRITER WRITES. So removing `- skills` to hand the domain to
# plugins would not stand a writer down — it would re-arm two of them, refill
# the tree, and double-load every skill against its plugin twin. A third state
# is the only way to say "nobody writes this".
domain_retired() {
    _apm_key_lists retired "$1"
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
