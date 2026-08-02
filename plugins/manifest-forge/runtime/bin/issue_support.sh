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
#   GIT_OPS_BIN, TRACKER_OPS_BIN, ISSUE_SUPPORT_CONFIG, ISSUE_SUPPORT_LABELS,
#   ISSUE_SUPPORT_TEMPLATE, ISSUE_SUPPORT_INTERACTIVE (0|1)

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "issue-support: $*" >&2; else printf '%s\n' "issue-support: $*" >&2; fi; }

FORGE_RUNTIME_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
FORGE_CONFIG_DIR="$FORGE_RUNTIME_DIR/config"
FORGE_STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/manifest/forge"
export FORGE_RUNTIME_DIR FORGE_CONFIG_DIR FORGE_STATE_DIR
SCRIPT_DIR="$FORGE_RUNTIME_DIR/bin"
GIT_OPS_BIN="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
TRACKER_OPS_BIN="${TRACKER_OPS_BIN:-${SCRIPT_DIR}/tracker_ops.sh}"
CONFIG_FILE="${ISSUE_SUPPORT_CONFIG:-${XDG_CONFIG_HOME:-${HOME}/.config}/manifest/forge/issue_support.json}"
ISSUE_HOOKS_STATE="${ISSUE_HOOKS_STATE:-${XDG_CONFIG_HOME:-${HOME}/.config}/manifest/forge/issue_hooks.json}"
TEMPLATE_FILE="${ISSUE_SUPPORT_TEMPLATE:-${FORGE_RUNTIME_DIR}/references/issue-support-issue.md}"

# Ordered status lifecycle (forward-only). Index = rank. (canonical labels.json set)
LIFECYCLE=("planned" "in-progress" "needs-review" "done")
MARKER_PREFIX="<!-- issue-support:sync v1"
export TEMPLATE_FILE MARKER_PREFIX

usage() {
    cat << 'USAGE'
Usage: issue_support.sh <subcommand> [options]

  sync-pr <N> [--dry-run] [--no-create]       Sync linked issues for opened PR/MR N
  sync-commit <SHA|HEAD> [--dry-run] [--no-create]  Sync linked issues for a commit
  resolve <--pr N|--commit SHA|--branch NAME> [--json]  Print resolved issue refs

Fail-open: sync-* always exit 0. Config: XDG Forge JSON overlays.
USAGE
}

# ---- helpers ---------------------------------------------------------------

git_ops() { "${GIT_OPS_BIN}" "$@"; }

# cfg_get <skill> <key> <default> — read tool_policies.<skill>.<key>
# overlay_has <skill> <key> -- does the user-scope overlay define this key?
# Separate from cfg_get's read so "present but false" stays distinguishable from
# "absent": folding them together would make it impossible to turn a hook OFF
# via the overlay once the package config said true.
overlay_has() {
    python3 - "${ISSUE_HOOKS_STATE}" "$1" "$2" << 'OV' 2> /dev/null
import json, sys
path, skill, key = sys.argv[1:4]
try:
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream) or {}
    pol = (data.get("tool_policies", {}) or {}).get(skill, {}) or {}
    sys.exit(0 if key in pol else 1)
except Exception:
    sys.exit(1)
OV
}

cfg_get() {
    local skill="$1" key="$2" default="$3" src="${CONFIG_FILE}"
    # Overlay first, package config second. A key absent from the overlay falls
    # through, so the overlay only carries what the user actually set.
    if [[ -f "${ISSUE_HOOKS_STATE}" ]] && overlay_has "${skill}" "${key}"; then
        src="${ISSUE_HOOKS_STATE}"
    fi
    [[ -f "${src}" ]] || {
        printf '%s' "${default}"
        return 0
    }
    python3 - "${src}" "${skill}" "${key}" "${default}" << 'PY' 2> /dev/null || printf '%s' "${default}"
import json, sys
path, skill, key, default = sys.argv[1:5]
try:
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream) or {}
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

# Remaining command implementation is sourced from the same bundle.
# shellcheck disable=SC1091
source "$FORGE_RUNTIME_DIR/bin/lib/issue_support_actions.sh"
