#!/usr/bin/env bash
# apm_ownership_report.sh — T010/FR-015/SC-006: which pipeline owns each
# deployed area, and is any area claimed by two?
#
# Delivered BEFORE the coexistence window, not after it. A diagnostic that
# arrives once the migration is finished polices a window that has already
# closed — it would only ever confirm the end state, never catch the transition
# going wrong, which is the only time the answer is in doubt.
#
# The two failure states this names:
#
#   DOUBLE-CLAIMED — the legacy writer and APM both write the area. This is the
#     drift the whole feature exists to remove: two pipelines, two ownership
#     models, one directory.
#   UNOWNED — neither writes it. Expected and safe DURING Phase 2 (the domain is
#     gated but APM has not arrived yet); a bug at any other time, because the
#     area silently stops updating and nothing says so.
#
# Read-only. Consumed by /env-check and /config-audit.
set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "apm_ownership_report.sh: $*" >&2; else printf '%s\n' "apm_ownership_report.sh: $*" >&2; fi; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: apm_ownership_report.sh [--json]

Report which pipeline owns each deployed domain, flagging any domain
claimed by both (drift) or by neither (silently not updating).

  --json   Machine-readable output.

Exit: 0 all domains have exactly one owner; 1 any domain double-claimed
or unowned. Read-only — never writes.
USAGE
    exit 0
fi

JSON=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)
            JSON=true
            shift
            ;;
        *)
            # Silently ignoring an unknown flag is how a typo'd --jsonn hands
            # human-readable text to a caller that asked for JSON.
            err "unknown argument: $1 (see --help)"
            exit 2
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ROOT="${MANIFEST_ROOT:-}"
if [[ -z "$ROOT" ]] && git -C "$SCRIPT_DIR" rev-parse --show-toplevel > /dev/null 2>&1; then
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
fi

# shellcheck disable=SC1090,SC1091
for _lib in "$ROOT/configs/claude/scripts/apm_domains_lib.sh" \
    "$SCRIPT_DIR/apm_domains_lib.sh" "$HOME/.claude/scripts/apm_domains_lib.sh"; do
    [[ -f "$_lib" ]] && {
        source "$_lib"
        break
    }
done
unset _lib

if ! declare -f apm_owns_domain > /dev/null 2>&1; then
    err "could not load apm_domains_lib.sh — cannot determine ownership"
    exit 1
fi

# Known domains and the deployed path each corresponds to. Kept explicit rather
# than derived: a domain that exists but is absent from this list would be
# reported as fine while being owned by nobody.
DOMAINS=("skills")
declare_path() {
    case "$1" in
        skills) echo "$HOME/.claude/skills" ;;
        *) echo "" ;;
    esac
}

# Does the LEGACY pipeline still write this domain? It stands down exactly when
# APM owns it, so this is the complement — derived from the same registry both
# writers consult, rather than a second hand-maintained list that could disagree.
legacy_writes() { ! apm_owns_domain "$1"; }

# Has APM actually deployed the domain? Ownership in the registry is an
# intention; the lockfile is the evidence. Distinguishing them is the whole
# point of the UNOWNED state.
LOCKFILE="${APM_LOCKFILE:-$HOME/.apm/apm.lock.yaml}"
apm_deployed() {
    local domain="$1"
    [[ -f "$LOCKFILE" ]] || return 1
    grep -q "\.claude/${domain}" "$LOCKFILE" 2> /dev/null
}

# Files present in a domain that the lockfile does NOT claim. Domain-level
# ownership is not enough: a domain can be gated and apm-deployed — reporting a
# clean single owner — while individual entries inside it belong to nobody,
# because the legacy writer has stood down and apm declined to adopt them.
#
# This is not hypothetical. Activating SC-006 hit exactly it: apm skipped
# ai-hooks-integration (its deployed copy held local __pycache__/.pytest_cache
# that apm will not adopt), emitting one easily-missed "[!] 1 file skipped" line.
# Without this check the report would have said "apm, exit 0" over an orphan.
#
# Entries other tools own are excluded by name, not guessed at: ~/.claude/skills
# legitimately holds foreign installs (e.g. .system, which is Codex's).
unowned_entries() {
    local domain="$1" path="$2" entry base
    [[ -d "$path" ]] || return 0
    [[ -f "$LOCKFILE" ]] || return 0
    for entry in "$path"/*/; do
        [[ -d "$entry" ]] || continue
        base="$(basename "$entry")"
        [[ "$base" == .* ]] && continue
        grep -q "\.claude/${domain}/${base}\b" "$LOCKFILE" 2> /dev/null || echo "$base"
    done
}

rc=0
rows=()
for d in "${DOMAINS[@]}"; do
    path="$(declare_path "$d")"
    legacy=false
    apm=false
    legacy_writes "$d" && legacy=true
    apm_deployed "$d" && apm=true

    if [[ "$legacy" == true && "$apm" == true ]]; then
        status="DOUBLE-CLAIMED"
        rc=1
    elif [[ "$legacy" == false && "$apm" == false ]]; then
        status="UNOWNED"
        rc=1
    elif [[ "$apm" == true ]]; then
        # Adopted, but completely? A partial adoption leaves orphans owned by
        # neither pipeline, which is the drift condition at file granularity.
        orphans="$(unowned_entries "$d" "$path")"
        if [[ -n "$orphans" ]]; then
            status="PARTIAL"
            rc=1
        else
            status="apm"
        fi
    else
        status="legacy"
    fi
    rows+=("$d|$path|$status|$legacy|$apm")
done

if [[ "$JSON" == true ]]; then
    printf '{"domains":['
    first=true
    for row in ${rows[@]+"${rows[@]}"}; do
        IFS='|' read -r d path status legacy apm <<< "$row"
        [[ "$first" == true ]] || printf ','
        first=false
        printf '{"domain":"%s","path":"%s","owner":"%s","legacy_writes":%s,"apm_deployed":%s}' \
            "$d" "$path" "$status" "$legacy" "$apm"
    done
    printf '],"ok":%s}\n' "$([[ $rc -eq 0 ]] && echo true || echo false)"
    exit "$rc"
fi

# Literal tilde via a variable: an inline \~ in the replacement is emitted
# as a backslash-tilde, and an unescaped ~ would tilde-expand.
HOME_TILDE="~"
printf '%-10s %-34s %s\n' "DOMAIN" "PATH" "OWNER"
for row in ${rows[@]+"${rows[@]}"}; do
    IFS='|' read -r d path status _ _ <<< "$row"
    printf '%-10s %-34s %s\n' "$d" "${path/#$HOME/$HOME_TILDE}" "$status"
done

if [[ $rc -ne 0 ]]; then
    echo ""
    for row in ${rows[@]+"${rows[@]}"}; do
        IFS='|' read -r d _ status _ _ <<< "$row"
        case "$status" in
            DOUBLE-CLAIMED)
                echo "! $d is written by BOTH pipelines — this is the drift condition."
                echo "  Gate the legacy writer (apm_domains.yml) or remove the APM package."
                ;;
            PARTIAL)
                echo "! $d is APM-owned but NOT fully adopted — these entries are owned by neither pipeline:"
                # Deliberate word-splitting: one entry per line is the payload.
                # shellcheck disable=SC2046
                printf '    %s\n' $(unowned_entries "$d" "$(declare_path "$d")")
                echo "  The legacy writer has stood down for this domain, so nothing updates them."
                echo "  Common cause: local build artifacts (__pycache__, .pytest_cache) in the"
                echo "  deployed copy — apm will not adopt a directory holding files it did not place."
                echo "  Clear them and re-install, or un-gate the domain."
                ;;
            UNOWNED)
                echo "! $d is written by NEITHER pipeline — it will silently stop updating."
                echo "  Expected only during the Phase 2 hand-over window."
                echo "  Hand it back with: apm_ungate_domain.sh $d --apply"
                ;;
        esac
    done
fi
exit "$rc"
