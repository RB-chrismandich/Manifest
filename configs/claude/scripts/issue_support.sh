#!/usr/bin/env bash
# issue_support.sh - Shared issue-support engine for the issue-linking hooks
#
# Platform-agnostic engine (sibling to git_ops.sh) that keeps the issue tracker
# in sync with development activity. Invoked by the issue-sync-pr and
# issue-sync-commit skills (and their hooks). FAIL-OPEN: sync-pr/sync-commit
# always exit 0 so a git action is never blocked.
#
# Subcommands:
#   sync-pr <N> [--dry-run] [--no-create]      Sync linked issues for an opened PR/MR
#   sync-commit <SHA|HEAD> [--dry-run] [--no-create]  Sync linked issues for a commit
#   resolve <--pr N | --commit SHA | --branch NAME> [--json]  Resolve issue refs only
#
# Env overrides (testing seams):
#   GIT_OPS_BIN, GIT_PLATFORM_BIN, ISSUE_SUPPORT_CONFIG, ISSUE_SUPPORT_LABELS,
#   ISSUE_SUPPORT_TEMPLATE, ISSUE_SUPPORT_INTERACTIVE (0|1)

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "issue-support: $*" >&2; else printf '%s\n' "issue-support: $*" >&2; fi; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_OPS_BIN="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
GIT_PLATFORM_BIN="${GIT_PLATFORM_BIN:-${SCRIPT_DIR}/git_platform.sh}"
CONFIG_FILE="${ISSUE_SUPPORT_CONFIG:-${SCRIPT_DIR}/../config/command_config.yml}"
TEMPLATE_FILE="${ISSUE_SUPPORT_TEMPLATE:-${SCRIPT_DIR}/templates/issue_support_issue.md}"

# Ordered status lifecycle (forward-only). Index = rank. (canonical labels.yml set)
LIFECYCLE=("planned" "in-progress" "needs-review" "done")
MARKER_PREFIX="<!-- issue-support:sync v1"

usage() {
    cat << 'USAGE'
Usage: issue_support.sh <subcommand> [options]

  sync-pr <N> [--dry-run] [--no-create]       Sync linked issues for opened PR/MR N
  sync-commit <SHA|HEAD> [--dry-run] [--no-create]  Sync linked issues for a commit
  resolve <--pr N|--commit SHA|--branch NAME> [--json]  Print resolved issue refs

Fail-open: sync-* always exit 0. Config: command_config.yml tool_policies.
USAGE
}

# ---- helpers ---------------------------------------------------------------

git_ops() { "${GIT_OPS_BIN}" "$@"; }

# cfg_get <skill> <key> <default> — read tool_policies.<skill>.<key>
cfg_get() {
    local skill="$1" key="$2" default="$3"
    [[ -f "${CONFIG_FILE}" ]] || {
        printf '%s' "${default}"
        return 0
    }
    python3 - "${CONFIG_FILE}" "${skill}" "${key}" "${default}" << 'PY' 2> /dev/null || printf '%s' "${default}"
import sys, yaml
path, skill, key, default = sys.argv[1:5]
try:
    data = yaml.safe_load(open(path)) or {}
    val = (data.get("tool_policies", {}) or {}).get(skill, {}) or {}
    out = val.get(key, default)
    if isinstance(out, bool):
        out = "true" if out else "false"
    print("" if out is None else out, end="")
except Exception:
    print(default, end="")
PY
}

# label_rank <label> — echo numeric rank (0 if unknown/empty)
label_rank() {
    local want="$1" i
    for i in "${!LIFECYCLE[@]}"; do
        [[ "${LIFECYCLE[$i]}" == "${want}" ]] && {
            printf '%s' "$((i + 1))"
            return 0
        }
    done
    printf '0'
}

# is_interactive — honor override, else check stdin is a tty
is_interactive() {
    if [[ -n "${ISSUE_SUPPORT_INTERACTIVE:-}" ]]; then
        [[ "${ISSUE_SUPPORT_INTERACTIVE}" == "1" ]]
    else
        [[ -t 0 ]]
    fi
}

# run_with_timeout <seconds> <cmd...> — bound a command; passthrough if no timeout tool
run_with_timeout() {
    local secs="$1"
    shift
    if command -v timeout > /dev/null 2>&1; then
        timeout "${secs}" "$@"
    elif command -v gtimeout > /dev/null 2>&1; then
        gtimeout "${secs}" "$@"
    else
        "$@"
    fi
}

# Current branch (best-effort)
current_branch() { git rev-parse --abbrev-ref HEAD 2> /dev/null || printf ''; }

# Current branch's open PR/MR number (best-effort; empty if none)
current_pr_number() {
    local platform="$1" n=""
    if [[ "${platform}" == "github" ]]; then
        n=$(git_ops pr-view --json number --jq '.number' 2> /dev/null || true)
    else
        n=$(git_ops pr-view --output json 2> /dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("iid",""))' 2> /dev/null || true)
    fi
    printf '%s' "${n}" | grep -oE '^[0-9]+$' || true
}

# Normalize an issue-view payload (gh or glab JSON) → "number|state|labels-csv|title"
# Reads raw JSON on stdin. Empty output = not found.
# NOTE: uses `python3 -c` (not a heredoc) so the piped JSON stays on stdin.
NORMALIZE_PY='
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
num = d.get("number") or d.get("iid") or d.get("id") or ""
state = (d.get("state") or "").lower()
if state in ("open", "opened"):
    state = "open"
elif state == "closed":
    state = "closed"
if d.get("locked") or d.get("discussion_locked"):
    state = "locked"
names = []
for L in (d.get("labels") or []):
    names.append(L.get("name", "") if isinstance(L, dict) else str(L))
labels = ",".join(n for n in names if n)
title = (d.get("title") or "").replace("|", "/").replace(chr(10), " ")
print("%s|%s|%s|%s" % (num, state, labels, title))
'
normalize_issue() { python3 -c "${NORMALIZE_PY}" 2> /dev/null || true; }

# Fetch a normalized issue record for number N. Echo "number|state|labels|title" or "".
issue_record() {
    local n="$1" platform="$2" raw=""
    if [[ "${platform}" == "github" ]]; then
        raw=$(git_ops issue-view "${n}" --json number,state,labels,title 2> /dev/null || true)
    else
        raw=$(git_ops issue-view "${n}" --output json 2> /dev/null || true)
    fi
    [[ -z "${raw}" ]] && return 0
    printf '%s' "${raw}" | normalize_issue
}

# Extract issue numbers referenced in a blob of text (#N, Closes/Fixes/Resolves #N)
extract_refs() {
    grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?)?[[:space:]]*#[0-9]+' |
        grep -oE '#[0-9]+' | tr -d '#' | sort -un || true
}

# Closing-verb refs ONLY (Closes/Fixes/Resolves #N) — the strong subset of extract_refs.
# Bare #N mentions ("part of epic #164") must never earn a closing keyword or a label
# transition: merging the PR would close issues it does not implement.
extract_closing_refs() {
    grep -oiE '(close[sd]?|fix(e[sd])?|resolve[sd]?)[[:space:]]+#[0-9]+' |
        grep -oE '#[0-9]+' | tr -d '#' | sort -un || true
}

# current status label of a normalized record (first lifecycle label found)
record_label() {
    local labels="$1" l
    [[ -z "${labels}" ]] && {
        printf ''
        return 0
    }
    local arr=()
    IFS=',' read -ra arr <<< "${labels}"
    for l in "${arr[@]+"${arr[@]}"}"; do
        [[ "$(label_rank "${l}")" != "0" ]] && {
            printf '%s' "${l}"
            return 0
        }
    done
    printf ''
}

# ---- summary accumulation --------------------------------------------------
declare -a ACTIONS=()
record_action() { ACTIONS+=("$1"); }
print_summary() {
    local prefix=""
    [[ "${DRY_RUN:-0}" == "1" ]] && prefix="(dry-run) "
    local line
    for line in "${ACTIONS[@]+"${ACTIONS[@]}"}"; do
        echo "${prefix}issue-support: ${line}"
    done
}

# ---- core actions ----------------------------------------------------------

# transition_issue <n> <current-label> <target-label> <platform>
transition_issue() {
    local n="$1" cur="$2" target="$3" platform="$4"
    local cur_rank target_rank
    cur_rank=$(label_rank "${cur}")
    target_rank=$(label_rank "${target}")
    if [[ "${cur_rank}" -ge "${target_rank}" ]]; then
        record_action "#${n} transition ${cur:-none}→${target} [skipped] (already at/after target)"
        return 0
    fi
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        record_action "#${n} transition ${cur:-none}→${target} [applied]"
        return 0
    fi
    local args=(--add-label "${target}")
    [[ -n "${cur}" ]] && args+=(--remove-label "${cur}")
    if git_ops issue-edit "${n}" "${args[@]}" > /dev/null 2>&1; then
        record_action "#${n} transition ${cur:-none}→${target} [applied]"
    else
        record_action "#${n} transition ${cur:-none}→${target} [failed] (label update error)"
    fi
}

# comment_backlink <n> <context-key> <body> <platform> — idempotent via marker
comment_backlink() {
    local n="$1" ctxkey="$2" body="$3" platform="$4"
    local marker="${MARKER_PREFIX} ${ctxkey} -->"
    local existing=""
    if [[ "${platform}" == "github" ]]; then
        existing=$(git_ops issue-view "${n}" --json comments 2> /dev/null || true)
    else
        existing=$(git_ops issue-view "${n}" --comments 2> /dev/null || true)
    fi
    if printf '%s' "${existing}" | grep -qF "${marker}"; then
        record_action "#${n} comment back-link [skipped] (marker already present)"
        return 0
    fi
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        record_action "#${n} comment back-link [applied]"
        return 0
    fi
    if git_ops issue-comment "${n}" --body "${body}"$'\n\n'"${marker}" > /dev/null 2>&1; then
        record_action "#${n} comment back-link [applied]"
    else
        record_action "#${n} comment back-link [failed] (comment error)"
    fi
}

# ensure_closing_keyword <pr> <issue-n> <platform>
ensure_closing_keyword() {
    local pr="$1" n="$2" platform="$3" body=""
    if [[ "${platform}" == "github" ]]; then
        body=$(git_ops pr-view "${pr}" --json body --jq '.body' 2> /dev/null || true)
    else
        body=$(git_ops pr-view "${pr}" --output json 2> /dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("description",""))' 2> /dev/null || true)
    fi
    if printf '%s' "${body}" | grep -qiE "(close[sd]?|fix(e[sd])?|resolve[sd]?)[[:space:]]+#${n}([^0-9]|$)"; then
        record_action "PR #${pr} closing-keyword Closes #${n} [skipped] (already present)"
        return 0
    fi
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        record_action "PR #${pr} closing-keyword Closes #${n} [applied]"
        return 0
    fi
    local newbody="${body}"$'\n\n'"Closes #${n}"
    if git_ops pr-edit "${pr}" --body "${newbody}" > /dev/null 2>&1; then
        record_action "PR #${pr} closing-keyword Closes #${n} [applied]"
    else
        record_action "PR #${pr} closing-keyword Closes #${n} [failed] (PR not editable — add 'Closes #${n}' manually)"
    fi
}

# ---- resolution ------------------------------------------------------------

# resolve_candidates <branch> <pr|""> <commit|""> — echo candidate numbers (one per line)
# Emits one "number|source" per resolved candidate (source: branch-prefix |
# pr-body | commit-message), de-duplicated by number keeping the first source.
resolve_candidates() {
    local branch="$1" pr="$2" commit="$3" platform="$4"
    local -a out=()
    # 1) branch-number prefix (strip leading zeros: 017-foo → issue #17)
    if [[ "${branch}" =~ ^([0-9]+)- ]]; then
        out+=("$((10#${BASH_REMATCH[1]}))|branch-prefix|strong")
    fi
    # 2) PR/MR body references
    if [[ -n "${pr}" ]]; then
        local body=""
        if [[ "${platform}" == "github" ]]; then
            body=$(git_ops pr-view "${pr}" --json body --jq '.body' 2> /dev/null || true)
        else
            body=$(git_ops pr-view "${pr}" --output json 2> /dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("description",""))' 2> /dev/null || true)
        fi
        # closing-verb refs first (strong wins the dedup), then bare mentions as weak
        while IFS= read -r r; do [[ -n "${r}" ]] && out+=("${r}|pr-body|strong"); done < <(printf '%s' "${body}" | extract_closing_refs)
        while IFS= read -r r; do [[ -n "${r}" ]] && out+=("${r}|pr-body|weak"); done < <(printf '%s' "${body}" | extract_refs)
    fi
    # 3) commit-message references + trailers
    if [[ -n "${commit}" ]]; then
        local msg
        msg=$(git log -1 --format='%B' "${commit}" 2> /dev/null || true)
        while IFS= read -r r; do [[ -n "${r}" ]] && out+=("${r}|commit-message|strong"); done < <(printf '%s' "${msg}" | extract_closing_refs)
        while IFS= read -r r; do [[ -n "${r}" ]] && out+=("${r}|commit-message|weak"); done < <(printf '%s' "${msg}" | extract_refs)
    fi
    printf '%s\n' "${out[@]+"${out[@]}"}" | awk -F'|' '$1 ~ /^[0-9]+$/ && !seen[$1]++' || true
}

# ---- platform gate ---------------------------------------------------------
detect_platform() {
    local p
    p=$(bash "${GIT_PLATFORM_BIN}" 2> /dev/null || printf 'git')
    printf '%s' "${p}"
}

# ---- create flow (US3) -----------------------------------------------------

render_template() {
    local branch="$1" pr="$2" commit="$3"
    local link="branch \`${branch}\`"
    [[ -n "${pr}" ]] && link="PR #${pr} on branch \`${branch}\`"
    [[ -n "${commit}" ]] && link="commit ${commit} on branch \`${branch}\`"
    if [[ -f "${TEMPLATE_FILE}" ]]; then
        sed -e "s|{{BRANCH}}|${branch}|g" -e "s|{{LINK}}|${link}|g" -e "s|{{PR}}|${pr}|g" -e "s|{{COMMIT}}|${commit}|g" "${TEMPLATE_FILE}"
    else
        printf '## Context\n\nTracking work on %s.\n\n## Acceptance Criteria\n\n- [ ] Define acceptance criteria\n' "${link}"
    fi
}

# offer_create <branch> <pr> <commit> <platform> — dedup, confirm, create.
# On reuse or successful creation, sets the global NEW_ISSUE to that issue number
# so sync_core can run the normal sync lifecycle on it (FR-009c).
NEW_ISSUE=""
offer_create() {
    local branch="$1" pr="$2" commit="$3" platform="$4"
    NEW_ISSUE=""
    if [[ "${NO_CREATE:-0}" == "1" ]]; then
        record_action "create-issue [skipped] (--no-create)"
        return 0
    fi
    # dedup: search for an existing open issue matching the branch
    local existing num=""
    existing=$(git_ops issue-list --search "${branch}" 2> /dev/null | head -1 || true)
    if [[ -n "${existing}" ]]; then
        num=$(printf '%s' "${existing}" | grep -oE '[0-9]+' | head -1 || true)
        record_action "create-issue [skipped] (existing match reused: #${num:-?})"
        NEW_ISSUE="${num}"
        return 0
    fi
    if ! is_interactive; then
        record_action "create-issue [skipped] (non-interactive; no tracking issue linked)"
        return 0
    fi
    printf 'issue-support: no tracking issue found. Create one from branch %s? [y/N] ' "${branch}" >&2
    local reply=""
    read -r reply || true
    if [[ ! "${reply}" =~ ^[Yy] ]]; then
        record_action "create-issue [skipped] (declined)"
        return 0
    fi
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        record_action "create-issue [applied] (dry-run, not created)"
        return 0
    fi
    local title="${branch}" bodyfile out
    bodyfile=$(mktemp)
    render_template "${branch}" "${pr}" "${commit}" > "${bodyfile}"
    if out=$(git_ops issue-create --title "${title}" --body-file "${bodyfile}" --label planned 2> /dev/null); then
        # gh/glab print the new issue URL; the trailing number is the issue id.
        num=$(printf '%s' "${out}" | grep -oE '[0-9]+' | tail -1 || true)
        record_action "create-issue [applied] (#${num:-?}, labeled planned, from template)"
        NEW_ISSUE="${num}"
    else
        record_action "create-issue [failed] (issue-create error)"
    fi
    rm -f "${bodyfile}"
}

# process_issue <n> <kind> <pr> <target> <ctxkey> <body> <platform>
# Apply the normal sync to a single issue (transition + comment + closing keyword).
process_issue() {
    local n="$1" kind="$2" pr="$3" target="$4" ctxkey="$5" body="$6" platform="$7" strength="${8:-strong}"
    local rec state cur _num _labels _title
    rec=$(issue_record "${n}" "${platform}")
    if [[ -z "${rec}" ]]; then
        record_action "#${n} [skipped] (issue not found)"
        return 0
    fi
    IFS='|' read -r _num state _labels _title <<< "${rec}"
    if [[ "${state}" == "closed" || "${state}" == "locked" ]]; then
        record_action "#${n} [skipped] (issue ${state})"
        return 0
    fi
    cur=$(record_label "${_labels}")
    # commit trigger only advances issues already labeled 'planned'
    if [[ "${kind}" == "commit" && "$(label_rank "${cur}")" == "0" ]]; then
        record_action "#${n} [skipped] (unlabeled; outside managed lifecycle)"
        return 0
    fi
    # Weak refs (bare #N mentions) get the back-link only: no label transition, no closing
    # keyword — the PR references the issue, it does not implement it.
    if [[ "${strength}" == "strong" ]]; then
        transition_issue "${n}" "${cur}" "${target}" "${platform}"
    fi
    comment_backlink "${n}" "${ctxkey}" "${body}" "${platform}"
    if [[ "${kind}" == "pr" && "${strength}" == "strong" ]]; then
        ensure_closing_keyword "${pr}" "${n}" "${platform}"
    fi
}

# ---- sync orchestration ----------------------------------------------------

# sync_core <kind> <pr|""> <commit|""> — shared body for sync-pr / sync-commit
sync_core() {
    local kind="$1" pr="$2" commit="$3"
    local platform branch target ctxkey body
    platform=$(detect_platform)
    if [[ "${platform}" != "github" && "${platform}" != "gitlab" ]]; then
        err "no GitHub/GitLab remote detected; nothing to sync"
        return 0
    fi
    branch=$(current_branch)

    if [[ "${kind}" == "pr" ]]; then
        target="needs-review"
        ctxkey="pr=${pr}"
        body="Tracked in PR #${pr}."
    else
        target="in-progress"
        ctxkey="commit=${branch}"
        body="Work in progress on branch \`${branch}\`."
    fi

    local candidates=()
    while IFS= read -r _c; do [[ -n "${_c}" ]] && candidates+=("${_c}"); done \
        < <(resolve_candidates "${branch}" "${pr}" "${commit}" "${platform}")
    if [[ "${#candidates[@]}" -eq 0 ]]; then
        offer_create "${branch}" "${pr}" "${commit}" "${platform}"
        # A reused/created issue enters the normal sync lifecycle immediately (FR-009c).
        if [[ -n "${NEW_ISSUE}" ]]; then
            process_issue "${NEW_ISSUE}" "${kind}" "${pr}" "${target}" "${ctxkey}" "${body}" "${platform}"
        fi
        return 0
    fi

    local c n strength
    for c in "${candidates[@]}"; do # array-safe: non-empty (early-returned above)
        n="${c%%|*}"
        strength="${c##*|}"
        [[ "${strength}" == "strong" || "${strength}" == "weak" ]] || strength="strong"
        process_issue "${n}" "${kind}" "${pr}" "${target}" "${ctxkey}" "${body}" "${platform}" "${strength}"
    done
    return 0
}

# ---- subcommand parsing ----------------------------------------------------

DRY_RUN=0
NO_CREATE=0

parse_common_flags() {
    REMAIN=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                DRY_RUN=1
                shift
                ;;
            --no-create)
                NO_CREATE=1
                shift
                ;;
            *)
                REMAIN+=("$1")
                shift
                ;;
        esac
    done
}

# Inner worker (re-exec target): does the real sync in its own process so that
# (a) a soft timeout can bound it without losing the ACTIONS summary, and
# (b) any failure stays contained (parent treats it as a non-fatal warning).
run_inner() {
    local kind="$1" pr="$2" commit="$3"
    DRY_RUN="$4"
    NO_CREATE="$5"
    sync_core "${kind}" "${pr}" "${commit}"
    print_summary
}

cmd_sync_pr() {
    parse_common_flags "$@"
    local pr="${REMAIN[0]:-}"
    if [[ "$(cfg_get issue-sync-pr enabled false)" != "true" ]]; then
        err "issue-sync-pr disabled (set tool_policies.issue-sync-pr.enabled: true)"
        return 0
    fi
    # Self-resolve the current branch's PR when no number is given (hook convenience)
    if [[ -z "${pr}" ]]; then
        pr=$(current_pr_number "$(detect_platform)")
    fi
    [[ -n "${pr}" ]] || {
        err "sync-pr: no PR number given and none found for the current branch"
        return 0
    }
    local t
    t=$(cfg_get issue-sync-pr hook_timeout_seconds 5)
    [[ "${t}" =~ ^[0-9]+$ ]] || t=5
    run_with_timeout "${t}" bash "$0" __inner pr "${pr}" "" "${DRY_RUN}" "${NO_CREATE}" ||
        err "sync degraded to a warning (non-fatal or timed out); re-run heals (FR-017)"
}

cmd_sync_commit() {
    parse_common_flags "$@"
    local commit="${REMAIN[0]:-HEAD}"
    if [[ "$(cfg_get issue-sync-commit enabled false)" != "true" ]]; then
        err "issue-sync-commit disabled (set tool_policies.issue-sync-commit.enabled: true)"
        return 0
    fi
    local mode
    mode=$(cfg_get issue-sync-commit commit_hook_mode sync)
    if [[ "${mode}" == "background" ]]; then
        err "commit_hook_mode=background is reserved for a future release; running sync"
    fi
    local t
    t=$(cfg_get issue-sync-commit hook_timeout_seconds 5)
    [[ "${t}" =~ ^[0-9]+$ ]] || t=5
    run_with_timeout "${t}" bash "$0" __inner commit "" "${commit}" "${DRY_RUN}" "${NO_CREATE}" ||
        err "sync degraded to a warning (non-fatal or timed out); re-run heals (FR-017)"
}

cmd_resolve() {
    local pr="" commit="" branch="" json=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --pr)
                pr="$2"
                shift 2
                ;;
            --commit)
                commit="$2"
                shift 2
                ;;
            --branch)
                branch="$2"
                shift 2
                ;;
            --json)
                json=1
                shift
                ;;
            *) shift ;;
        esac
    done
    [[ -z "${branch}" ]] && branch=$(current_branch)
    local platform
    platform=$(detect_platform)
    local refs=()
    while IFS= read -r _n; do [[ -n "${_n}" ]] && refs+=("${_n}"); done \
        < <(resolve_candidates "${branch}" "${pr}" "${commit}" "${platform}")
    if [[ "${#refs[@]}" -eq 0 ]]; then
        if [[ "${json}" == "1" ]]; then echo "[]"; else err "no issue resolved"; fi
        return 3
    fi
    if [[ "${json}" == "1" ]]; then
        # Emit the full IssueRef per the data model: number, source, and (when the
        # tracker is reachable) exists/state/label validated via issue-view.
        printf '['
        local i num source rec state labels exists cur
        for i in "${!refs[@]}"; do
            num="${refs[$i]%%|*}"
            source="${refs[$i]#*|}"
            source="${source%%|*}"
            rec=$(issue_record "${num}" "${platform}")
            if [[ -n "${rec}" ]]; then
                IFS='|' read -r _ state labels _ <<< "${rec}"
                exists=true
                cur=$(record_label "${labels}")
            else
                exists=false
                state=""
                cur=""
            fi
            [[ "${i}" -gt 0 ]] && printf ','
            printf '{"number":%s,"source":"%s","exists":%s,"state":"%s","label":"%s"}' \
                "${num}" "${source}" "${exists}" "${state}" "${cur}"
        done
        printf ']\n'
    else
        local r
        for r in "${refs[@]}"; do printf '%s\n' "${r%%|*}"; done # array-safe: non-empty (returned 3 above)
    fi
    return 0
}

# ---- dispatch --------------------------------------------------------------

[[ $# -eq 0 ]] && {
    usage >&2
    exit 1
}
case "$1" in
    --help | -h | help)
        usage
        exit 0
        ;;
    sync-pr)
        shift
        cmd_sync_pr "$@"
        exit 0
        ;;
    sync-commit)
        shift
        cmd_sync_commit "$@"
        exit 0
        ;;
    resolve)
        shift
        cmd_resolve "$@"
        exit $?
        ;;
    __inner)
        shift
        run_inner "$@"
        exit 0
        ;; # internal re-exec target (timeout-bounded worker)
    *)
        err "Unknown subcommand: $1"
        usage >&2
        exit 1
        ;;
esac
