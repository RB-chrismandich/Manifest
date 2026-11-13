# shellcheck shell=bash
# External-transition comparison for pr_merge_loop.sh fingerprint state.

fingerprint_external_matches() {
    local before="${1:?before material required}" after="${2:?after material required}"
    local before_scope after_scope before_external after_external
    before_scope="$(printf '%s' "$before" | _jget scope_hash 2> /dev/null)" || return 1
    after_scope="$(printf '%s' "$after" | _jget scope_hash 2> /dev/null)" || return 1
    before_external="$(printf '%s' "$before" | _jget external_fingerprint 2> /dev/null)" || return 1
    after_external="$(printf '%s' "$after" | _jget external_fingerprint 2> /dev/null)" || return 1
    [[ "$before_scope" == "$after_scope" && "$before_external" == "$after_external" ]]
}
