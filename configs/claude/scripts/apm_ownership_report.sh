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

err() { printf 'apm_ownership_report.sh: %s\n' "$*" >&2; }

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

    # RETIRED short-circuits the whole matrix. Once a domain is handed to the
    # plugins, "written by neither pipeline" is the CORRECT end state, not the
    # drift condition -- and the UNOWNED advice ("hand it back with
    # apm_ungate_domain.sh") would walk a user straight back out of the cutover.
    if declare -f domain_retired > /dev/null 2>&1 && domain_retired "$d"; then
        status="retired"
    elif [[ "$legacy" == true && "$apm" == true ]]; then
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

# --- the additive owners (T1.11, spec 674) ---------------------------------
#
# Appended AFTER the two-writer matrix above, and only when there is something
# real to report. Adding them to DOMAINS unconditionally inverts the very
# failure this task targets: pre-cutover no bundle is installed and the harness
# tree does not exist, so both rows would read UNOWNED and turn /env-check red
# on a CORRECT machine. A permanently-red gate is a disabled gate in either
# direction -- two weeks of noise and a genuinely missing symlink is invisible.
#
# So each row is self-disabling on EVIDENCE, matching this script's existing
# rule that the registry states an intention and the filesystem states a fact.

PLUGINS_STATE="${CLAUDE_PLUGINS_STATE:-$HOME/.claude/plugins/installed_plugins.json}"
REGISTRY="${MANIFEST_SKILL_REGISTRY:-$HOME/.claude/config/skill_policies.yml}"
HARNESS_SKILLS="${MANIFEST_SKILLS_DIR:-$HOME/.manifest/skills}"

# Bundle names come from the REGISTRY, never from a name prefix. `manifest-*`
# looked like a safe assumption and was wrong on the very first run: the
# `stitch-design` bundle carries no prefix, so the report said 8 bundles with 9
# installed -- an undercount that reads as a partial install.
#
# Matched with the trailing colon so a key is matched and a mere value is not;
# keys are "<name>@<marketplace>". Deliberately grep and not python3 -- this
# script has no interpreter dependency today and the report must still run on a
# machine where that is what broke.
known_bundles() {
    [[ -r "$REGISTRY" ]] || return 0
    # `name` is a COPY. Mutating $0 in the middle rule made the last rule test
    # the STRIPPED line, which no longer starts with a space, so inb was cleared
    # after the very first bundle and the report claimed 1 of 9 installed.
    awk '/^bundles:/ {inb=1; next}
         inb && /^[^ ]/ {inb=0}
         inb && /^  [A-Za-z0-9_-]+:/ {name=$1; sub(/:$/, "", name); print name}' "$REGISTRY"
}

installed_manifest_bundles() {
    [[ -f "$PLUGINS_STATE" ]] || return 0
    local bundle
    while IFS= read -r bundle; do
        [[ -n "$bundle" ]] || continue
        grep -qE "\"${bundle}@[A-Za-z0-9_-]+\"[[:space:]]*:" "$PLUGINS_STATE" 2> /dev/null &&
            printf '%s\n' "$bundle"
    done < <(known_bundles)
}

# Sibling harness homes whose skills entry does NOT resolve into the tree.
# Devin is deliberately absent: its ~/.config/devin/skills is not created until
# Phase 4, so including it would redden every correct Phase-2 machine.
diverted_siblings() {
    local home_dir link
    for home_dir in "$HOME/.cursor" "$HOME/.gemini" "$HOME/.codex" "$HOME/.antigravity"; do
        link="$home_dir/skills"
        [[ -e "$link" || -L "$link" ]] || continue
        [[ "$(readlink "$link" 2> /dev/null || true)" == "$HARNESS_SKILLS" ]] || basename "$home_dir"
    done
}

# `|| true`: no installed bundle is the NORMAL pre-cutover state, but grep
# exits 1 on no-match and pipefail propagates it, so without this the report
# aborts with no output at all on every machine that has not cut over yet.
bundles="$(installed_manifest_bundles || true)"
if [[ -n "$bundles" ]]; then
    n_bundles="$(printf '%s\n' "$bundles" | wc -l | tr -d ' ')"
    # A name served by an installed bundle AND still present in ~/.claude/skills
    # double-loads: two SKILL.md under one name, no dedup, no error, and both
    # descriptions charged against the session listing budget.
    dupes=""
    for b in $bundles; do
        for sk in "$HOME/.claude/plugins/cache"/*/"$b"/skills/*/; do
            [[ -d "$sk" ]] || continue
            [[ -d "$HOME/.claude/skills/$(basename "$sk")" ]] && dupes="$dupes $(basename "$sk")"
        done
    done
    if [[ -n "$dupes" ]]; then
        rows+=("plugins|$HOME/.claude/plugins|DOUBLE-CLAIMED|true|false")
        rc=1
    else
        rows+=("plugins|$HOME/.claude/plugins ($n_bundles bundle(s))|plugins|false|false")
    fi
fi

if [[ -d "$HARNESS_SKILLS" ]]; then
    diverted="$(diverted_siblings)"
    if [[ -n "$diverted" ]]; then
        rows+=("harness-skills|$HARNESS_SKILLS|PARTIAL|false|false")
        rc=1
    else
        rows+=("harness-skills|$HARNESS_SKILLS|manifest|false|false")
    fi
fi

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
printf '%-15s %-34s %s\n' "DOMAIN" "PATH" "OWNER"
for row in ${rows[@]+"${rows[@]}"}; do
    IFS='|' read -r d path status _ _ <<< "$row"
    printf '%-15s %-34s %s\n' "$d" "${path/#$HOME/$HOME_TILDE}" "$status"
done

if [[ $rc -ne 0 ]]; then
    echo ""
    for row in ${rows[@]+"${rows[@]}"}; do
        IFS='|' read -r d _ status _ _ <<< "$row"
        case "$status" in
            DOUBLE-CLAIMED)
                if [[ "$d" == plugins ]]; then
                    echo "! these skills exist in BOTH an installed bundle and ~/.claude/skills:"
                    # Deliberate word-splitting: one name per line is the payload.
                    # shellcheck disable=SC2086
                    printf '    %s\n' $dupes
                    echo "  Both load, neither wins, and both descriptions are charged against"
                    echo "  the session listing budget. Remove the ~/.claude/skills copy."
                    continue
                fi
                echo "! $d is written by BOTH pipelines — this is the drift condition."
                echo "  Gate the legacy writer (apm_domains.yml) or remove the APM package."
                ;;
            PARTIAL)
                if [[ "$d" == harness-skills ]]; then
                    echo "! these harness homes do NOT resolve into $HARNESS_SKILLS:"
                    # shellcheck disable=SC2046
                    printf '    %s\n' $(diverted_siblings)
                    echo "  They are served by something else and will not see updates."
                    echo "  Re-run ./bootstrap.sh to repoint them."
                    continue
                fi
                echo "! $d is APM-owned but NOT fully adopted — these entries are owned by neither pipeline:"
                # Deliberate word-splitting: one entry per line is the payload.
                # shellcheck disable=SC2046
                printf '    %s\n' $(unowned_entries "$d" "$(declare_path "$d")")
                echo "  The legacy writer has stood down for this domain, so nothing updates them."
                echo "  Common cause: local build artifacts (__pycache__, .pytest_cache) in the"
                echo "  deployed copy — apm will not adopt a directory holding files it did not place."
                echo "  Clear them and re-install, or un-gate the domain."
                ;;
            retired)
                : # nothing to say: the plugins row above is the live owner
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
