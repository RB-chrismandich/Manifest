#!/usr/bin/env bash
# branch_clean.sh - Identify and (optionally) delete stale git branches
#
# Groups deletion candidates by reason — merged into the default branch,
# tracking a deleted remote ([gone]), or stale beyond a threshold — and deletes
# them only with --apply + confirmation. Dry-run by default. Local-only by
# default; remote deletion is opt-in. Protected and current branches are never
# proposed.
#
# Usage: branch_clean.sh [--apply] [--include-remote] [--stale-days N] \
#                        [--protect GLOB]... [--default BRANCH] [--yes] [--json]
#
#   --apply           Perform deletions (otherwise dry-run preview only).
#   --include-remote  Also delete the matching remote branch (opt-in).
#   --stale-days N    Staleness threshold (default: config / 90).
#   --protect GLOB    Extra protected branch glob (repeatable).
#   --default BRANCH  Override default-branch detection.
#   --yes             Skip the interactive confirmation prompt (for --apply).
#   --json            Machine-readable output.
#
# Exit codes: 0 = success; 2 = usage / not-a-git-repo error.
#
# Compatible with bash 3.2.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${BRANCH_CLEAN_CONFIG:-${SCRIPT_DIR}/../config/command_config.yml}"

APPLY=false
INCLUDE_REMOTE=false
STALE_DAYS=""
DEFAULT_BRANCH=""
ASSUME_YES=false
JSON_OUT=false
EXTRA_PROTECT=()

err() { echo "branch-clean: $*" >&2; }
usage_error() {
    err "$*"
    exit 2
}

usage() {
    cat << 'USAGE'
Usage: branch_clean.sh [--apply] [--include-remote] [--stale-days N]
                       [--protect GLOB]... [--default BRANCH] [--yes] [--json]

  --apply           Perform deletions (otherwise dry-run preview only)
  --include-remote  Also delete the matching remote branch (opt-in)
  --stale-days N    Staleness threshold (default: config / 90)
  --protect GLOB    Extra protected branch glob (repeatable)
  --default BRANCH  Override default-branch detection
  --yes             Skip the interactive confirmation prompt (for --apply)
  --json            Machine-readable output
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help | -h)
            usage
            exit 0
            ;;
        --apply)
            APPLY=true
            shift
            ;;
        --include-remote)
            INCLUDE_REMOTE=true
            shift
            ;;
        --stale-days)
            [[ $# -ge 2 ]] || usage_error "--stale-days needs an argument"
            STALE_DAYS="$2"
            shift 2
            ;;
        --protect)
            [[ $# -ge 2 ]] || usage_error "--protect needs a glob"
            EXTRA_PROTECT+=("$2")
            shift 2
            ;;
        --default)
            [[ $# -ge 2 ]] || usage_error "--default needs a branch"
            DEFAULT_BRANCH="$2"
            shift 2
            ;;
        --yes)
            ASSUME_YES=true
            shift
            ;;
        --json)
            JSON_OUT=true
            shift
            ;;
        -*) usage_error "unknown flag: $1" ;;
        *) usage_error "unexpected argument: $1" ;;
    esac
done

git rev-parse --git-dir > /dev/null 2>&1 || usage_error "not a git repository"

# Config defaults (stale_days + protected globs).
read_config() {
    [[ -f "$CONFIG" ]] || {
        echo "90"
        return 0
    }
    python3 - "$CONFIG" << 'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
bc = cfg.get("branch_clean") or {}
print(bc.get("stale_days", 90))
for g in bc.get("protected") or []:
    print(g)
PY
}

CONF="$(read_config)"
CONF_STALE="$(printf '%s\n' "$CONF" | head -1)"
[[ -n "$STALE_DAYS" ]] || STALE_DAYS="$CONF_STALE"

PROTECTED=()
while IFS='' read -r g; do [[ -n "$g" ]] && PROTECTED+=("$g"); done < <(printf '%s\n' "$CONF" | tail -n +2)
PROTECTED+=(${EXTRA_PROTECT[@]+"${EXTRA_PROTECT[@]}"})

detect_default() {
    if [[ -n "$DEFAULT_BRANCH" ]]; then
        echo "$DEFAULT_BRANCH"
        return 0
    fi
    local d
    d="$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2> /dev/null | sed 's@^refs/remotes/origin/@@')"
    if [[ -n "$d" ]]; then
        echo "$d"
        return 0
    fi
    for d in main master; do
        git show-ref --verify --quiet "refs/heads/$d" && {
            echo "$d"
            return 0
        }
    done
    git rev-parse --abbrev-ref HEAD 2> /dev/null || echo "main"
}

DEFAULT="$(detect_default)"
CURRENT="$(git rev-parse --abbrev-ref HEAD 2> /dev/null || echo '')"

is_protected() {
    local b="$1" g
    [[ "$b" == "$DEFAULT" || "$b" == "$CURRENT" ]] && return 0
    for g in ${PROTECTED[@]+"${PROTECTED[@]}"}; do
        # shellcheck disable=SC2053
        [[ "$b" == $g ]] && return 0
    done
    return 1
}

# Build "branch<TAB>reason" lines (reason priority merged > gone > stale).
classify() {
    local now b track ct age merged_list
    now="$(date +%s)"
    merged_list=" $(git branch --merged "$DEFAULT" --format '%(refname:short)' 2> /dev/null | tr '\n' ' ') "
    while IFS='' read -r line; do
        b="${line%% *}"
        track="${line#* }"
        [[ -n "$b" ]] || continue
        is_protected "$b" && continue
        if [[ "$merged_list" == *" $b "* ]]; then
            printf '%s\t%s\t%s\n' "$b" merged 0
            continue
        fi
        if [[ "$track" == *"[gone]"* ]]; then
            printf '%s\t%s\t%s\n' "$b" gone 0
            continue
        fi
        ct="$(git log -1 --format=%ct "$b" 2> /dev/null || echo "$now")"
        age=$(((now - ct) / 86400))
        if [[ "$age" -gt "$STALE_DAYS" ]]; then
            printf '%s\t%s\t%s\n' "$b" stale "$age"
        fi
    done < <(git for-each-ref --format '%(refname:short) %(upstream:track)' refs/heads 2> /dev/null)
}

delete_local() {
    # Safe delete (-d): refuses unmerged branches, honoring FR-020.
    git branch -d "$1" > /dev/null 2>&1
}
delete_remote() {
    # Nothing to delete if the remote ref is already absent (not a failure).
    git ls-remote --exit-code --heads origin "$1" > /dev/null 2>&1 || return 0
    git push origin --delete "$1" > /dev/null 2>&1
}

main() {
    local candidates
    candidates="$(classify)"
    local n_merged=0 n_gone=0 n_stale=0 total=0
    local -a names=() reasons=() ages=()
    while IFS=$'\t' read -r b r a; do
        [[ -n "$b" ]] || continue
        names+=("$b")
        reasons+=("$r")
        ages+=("$a")
        total=$((total + 1))
        case "$r" in merged) n_merged=$((n_merged + 1)) ;; gone) n_gone=$((n_gone + 1)) ;; stale) n_stale=$((n_stale + 1)) ;; esac
    done <<< "$candidates"

    local scope="local"
    $INCLUDE_REMOTE && scope="local+remote"
    local mode="dry-run"
    $APPLY && mode="apply"

    if $JSON_OUT; then
        local i first=true
        printf '{"mode":"%s","scope":"%s","default":"%s","candidates":[' "$mode" "$scope" "$DEFAULT"
        for ((i = 0; i < total; i++)); do
            $first || printf ','
            first=false
            printf '{"name":"%s","reason":"%s","age_days":%s}' "${names[$i]}" "${reasons[$i]}" "${ages[$i]}"
        done
        printf ']}\n'
    else
        echo "branch-clean ($mode) — scope: $scope, default: $DEFAULT"
        print_group merged "Merged into $DEFAULT" || true
        print_group gone "Gone upstream" || true
        print_group stale "Stale > ${STALE_DAYS}d" || true
        echo "Protected (never deleted): default=$DEFAULT, current=$CURRENT, globs=[${PROTECTED[*]-}]"
    fi

    [[ "$total" -eq 0 ]] && {
        $JSON_OUT || echo "Summary: 0 candidates."
        return 0
    }

    if ! $APPLY; then
        $JSON_OUT || echo "Summary: $total candidates (merged $n_merged, gone $n_gone, stale $n_stale); dry-run, nothing deleted."
        return 0
    fi

    # --apply path: confirm unless --yes.
    if ! $ASSUME_YES; then
        printf 'Delete %d local branch(es)%s? [y/N] ' "$total" "$($INCLUDE_REMOTE && echo ' and their remotes' || true)" >&2
        local ans=""
        IFS='' read -r ans < /dev/tty 2> /dev/null || ans=""
        case "$ans" in y | Y | yes | YES) ;; *)
            err "aborted"
            return 0
            ;;
        esac
    fi

    local i deleted=0 failed=0
    for ((i = 0; i < total; i++)); do
        local b="${names[$i]}" ok=true
        # Gate remote deletion on a successful local safe-delete: if `git branch
        # -d` refuses (unmerged), never delete the remote (which could still hold
        # unmerged commits). Local safe-delete is the safety check.
        if delete_local "$b"; then
            if $INCLUDE_REMOTE && ! delete_remote "$b"; then ok=false; fi
        else
            ok=false
        fi
        if $ok; then
            deleted=$((deleted + 1))
            $JSON_OUT || echo "  deleted  $b"
        else
            failed=$((failed + 1))
            $JSON_OUT || echo "  FAILED   $b (unmerged locally, or remote error; remote left intact)"
        fi
    done
    $JSON_OUT || echo "Summary: $total candidates; applied: $deleted deleted, $failed failed."
}

print_group() {
    local want="$1" title="$2" i shown=false
    for ((i = 0; i < ${#names[@]}; i++)); do
        if [[ "${reasons[$i]}" == "$want" ]]; then
            $shown || {
                echo "$title:"
                shown=true
            }
            if [[ "$want" == stale ]]; then
                printf '  - %-30s (stale, %sd) [delete-candidate]\n' "${names[$i]}" "${ages[$i]}"
            else
                printf '  - %-30s (%s) [delete-candidate]\n' "${names[$i]}" "$want"
            fi
        fi
    done
    $shown || return 1
}

main "$@"
