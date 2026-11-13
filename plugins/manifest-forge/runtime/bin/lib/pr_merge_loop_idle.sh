# shellcheck shell=bash
# Human-idle preflight and explicit disposition recording. Uses the existing
# fingerprint state format; observation failure never certifies idle.
# fingerprint_recorded_action <pr> <material> — print the action persisted
# alongside a still-matching fingerprint (empty when no valid state exists).
# cmd_run uses it to distinguish "unchanged because settled" (hand-human, a
# hard-gated merge) from "unchanged but in flight" (wait/revise/update-branch);
# only the former may advance the consecutive-empty counter.
fingerprint_recorded_action() {
    local pr="${1:?pr required}" material="${2:?material required}" path
    fingerprint_state_matches "$pr" "$material" || return 0
    path="$(fingerprint_state_path "$pr" "$material")" || return 0
    python3 - "$path" << 'PY' 2> /dev/null || true
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["action"])
PY
}

cmd_address_status() {
    local pr="${1:?pr required}" material disposition=actionable fingerprint
    material="$(collect_fingerprint_material "$pr")" || return 13
    if [[ "$(fingerprint_recorded_action "$pr" "$material")" == "hand-human" ]]; then
        disposition=blocked
    fi
    if [[ "${2:-}" == "--json" ]]; then
        fingerprint="$(printf '%s' "$material" | _jget fingerprint)" || return 13
        printf '{"status":"%s","fingerprint":"%s"}\n' "$disposition" "$fingerprint"
    elif [[ "$disposition" == blocked ]]; then
        printf 'blocked on human: #%s\n' "$pr"
    else
        printf 'actionable: #%s\n' "$pr"
    fi
}

cmd_record_human_blocked() {
    local pr="${1:?pr required}" expected="${2:?observed fingerprint required}" material fingerprint
    material="$(collect_fingerprint_material "$pr")" || return 13
    fingerprint="$(printf '%s' "$material" | _jget fingerprint)" || return 13
    if [[ "$expected" != "$fingerprint" ]]; then
        err "#$pr: material changed — human disposition not recorded"
        return 13
    fi
    persist_fingerprint_state "$pr" "$material" hand-human || return 13
    printf 'blocked on human: #%s\n' "$pr"
}
