#!/usr/bin/env bash
# cutover_snapshot.sh — T0.1 (spec 674): the restore path for the plugin cutover.
#
# Deliberately built from tar and find alone. Every rollback the four cutover
# designs proposed is CIRCULAR: they call `apm_ungate_domain.sh skills --apply`
# or `apm-dev-sync`, both of which the cutover retires, and apm_ungate_domain.sh
# additionally guards on the registry entry it is restoring, so it exits 1 the
# moment that entry moves to `retired:`. A backup that depends on bootstrap, apm
# or the plugin CLI is therefore not a backup — it is a second thing to restore.
#
# This is the ONLY rollback that survives Phase 5, which is why it is a hard
# prerequisite of Phase 0 rather than hygiene.
set -euo pipefail

err() { printf 'cutover_snapshot.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: cutover_snapshot.sh [--verify [FILE]] [--help]

Mechanism-independent backup of pre-cutover skill state. Uses only tar and
find -- never apm, bootstrap or the claude CLI, because a restore path that
shares a dependency with the migration is not a restore path.

  (no args)        Write pre-cutover-<ts>.tgz plus a .txt sidecar into
                   $MANIFEST_STATE_DIR (default ~/.manifest)
  --verify [FILE]  Extract the newest (or named) snapshot to a temp dir and
                   assert its SKILL.md count matches the sidecar
  --help           This text
USAGE
    exit 0
fi

STATE_DIR="${MANIFEST_STATE_DIR:-$HOME/.manifest}"

# Paths worth capturing. Each is optional: tar aborts on a missing operand, and
# on a default machine Devin is disabled and its config genuinely absent, so
# "missing" is the common case rather than an edge.
SNAPSHOT_PATHS=(
    ".claude/skills"
    ".claude/settings.json"
    ".claude/plugins/installed_plugins.json"
    ".apm/apm.lock.yaml"
    ".apm/apm.yml"
    ".config/devin/config.json"
)

# Sibling homes whose skills entry is a symlink into ~/.claude/skills. Recorded
# by target, not by existence: Phase 2 repoints these, and a rollback needs to
# know where they pointed before, not merely that they pointed somewhere.
SIBLING_HOMES=(cursor gemini codex antigravity)

# Populated by create_snapshot, consumed by write_sidecar.
CAPTURED_PATHS=()

verify_captured() {
    local tmp="$1" txt="$2" rel rc=0
    while IFS= read -r rel; do
        [[ -n "$rel" ]] || continue
        if [[ -d "$tmp/$rel" ]]; then
            if [[ -z "$(ls -A "$tmp/$rel" 2> /dev/null)" ]]; then
                err "captured directory is empty in the archive: $rel"
                rc=1
            fi
        elif [[ ! -s "$tmp/$rel" ]]; then
            err "captured file missing or empty in the archive: $rel"
            rc=1
        fi
    done < <(sed -n 's/^captured=//p' "$txt")

    # Restoring a corrupt settings.json is not a restore. Checked by content,
    # not just size, because the failure that motivated this was a non-empty
    # file full of garbage.
    local settings="$tmp/.claude/settings.json"
    if [[ -s "$settings" ]] && command -v python3 > /dev/null 2>&1; then
        if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$settings" 2> /dev/null; then
            err "captured file is not parseable JSON: .claude/settings.json"
            rc=1
        fi
    fi
    return "$rc"
}

count_skills() {
    find "$1" -mindepth 2 -maxdepth 2 -name SKILL.md 2> /dev/null | wc -l | tr -d ' '
}

link_target() {
    if [[ -L "$1" ]]; then readlink "$1"; else printf 'ABSENT'; fi
}

write_sidecar() {
    local txt="$1" tgz="$2" name rel
    {
        printf 'snapshot=%s\n' "$(basename "$tgz")"
        printf 'home=%s\n' "$HOME"
        printf 'skill_count=%s\n' "$(count_skills "$HOME/.claude/skills")"
        # What was actually archived, so --verify can re-check all of it rather
        # than one count. Absent optional paths are simply not listed, which is
        # why verify demands only what was genuinely captured.
        for rel in ${CAPTURED_PATHS[@]+"${CAPTURED_PATHS[@]}"}; do
            printf 'captured=%s\n' "$rel"
        done
        for name in "${SIBLING_HOMES[@]}"; do
            printf 'readlink_%s=%s\n' "$name" "$(link_target "$HOME/.$name/skills")"
        done
        printf 'readlink_devin=%s\n' "$(link_target "$HOME/.config/devin/skills")"
        if [[ -f "$HOME/.claude/plugins/installed_plugins.json" ]]; then
            printf 'installed_plugins=present\n'
        else
            printf 'installed_plugins=ABSENT\n'
        fi
    } > "$txt"
}

create_snapshot() {
    local ts tgz txt rel
    mkdir -p "$STATE_DIR"
    ts="$(date +%Y%m%d_%H%M%S)"
    tgz="$STATE_DIR/pre-cutover-$ts.tgz"
    txt="${tgz%.tgz}.txt"

    CAPTURED_PATHS=()
    for rel in "${SNAPSHOT_PATHS[@]}"; do
        [[ -e "$HOME/$rel" ]] && CAPTURED_PATHS+=("$rel")
    done
    if [[ ${#CAPTURED_PATHS[@]} -eq 0 ]]; then
        err "nothing to snapshot under $HOME - refusing to write an empty archive"
        return 1
    fi

    # The empty case returns above, so this cannot expand to nothing; the
    # ${a[@]+"${a[@]}"} form is used anyway because Bash 3.2 + set -u treats a
    # bare empty-array expansion as an unbound variable (specs/003 FR-011).
    if ! tar czf "$tgz" -C "$HOME" ${CAPTURED_PATHS[@]+"${CAPTURED_PATHS[@]}"}; then
        err "tar failed writing $tgz"
        return 1
    fi
    write_sidecar "$txt" "$tgz"
    printf 'Snapshot written: %s\n' "$tgz"
    printf 'Sidecar:          %s\n' "$txt"
}

newest_snapshot() {
    find "$STATE_DIR" -maxdepth 1 -name 'pre-cutover-*.tgz' 2> /dev/null |
        sort | tail -1
}

verify_snapshot() {
    local tgz="${1:-}" txt tmp expected actual rc=0
    [[ -n "$tgz" ]] || tgz="$(newest_snapshot)"
    if [[ -z "$tgz" || ! -f "$tgz" ]]; then
        err "no snapshot found under $STATE_DIR - run without arguments first"
        return 1
    fi
    txt="${tgz%.tgz}.txt"
    if [[ ! -f "$txt" ]]; then
        err "sidecar missing for $tgz - cannot verify a snapshot with no recorded count"
        return 1
    fi

    expected="$(sed -n 's/^skill_count=//p' "$txt")"
    if [[ -z "$expected" ]]; then
        err "sidecar $txt records no skill_count"
        return 1
    fi

    tmp="$(mktemp -d "${TMPDIR:-/tmp}/cutover_verify.XXXXXX")"
    if ! tar xzf "$tgz" -C "$tmp" 2> /dev/null; then
        err "cannot extract $tgz - the archive is unreadable or truncated"
        rm -rf "$tmp"
        return 1
    fi

    actual="$(count_skills "$tmp/.claude/skills")"
    if [[ "$actual" != "$expected" ]]; then
        err "SKILL.md count mismatch: sidecar says $expected, archive holds $actual"
        rc=1
    fi
    verify_captured "$tmp" "$txt" || rc=1
    if [[ "$rc" -eq 0 ]]; then
        printf 'OK: %s holds %s readable SKILL.md files and every captured path\n' \
            "$(basename "$tgz")" "$actual"
    fi
    rm -rf "$tmp"
    return "$rc"
}

main() {
    case "${1:-}" in
        --verify) verify_snapshot "${2:-}" ;;
        "") create_snapshot ;;
        *)
            err "unknown argument: $1 (try --help)"
            return 2
            ;;
    esac
}

main "$@"
