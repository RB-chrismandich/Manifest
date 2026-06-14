#!/usr/bin/env bash
# install_issue_hooks.sh - Enable/disable the issue-linking hooks (opt-in).
#
# Installs two surfaces:
#   1) A unified PostToolUse hook (cross-tool) routed through issue_support_hook.sh
#      -> fires the engine on PR-create and (optionally) commit commands.
#   2) (--native) A guarded git post-commit hook for commits made outside an AI tool.
#
# Idempotent and reversible. Default-off: --enable flips the runtime gate.
#
# Usage:
#   install_issue_hooks.sh --enable [--native] [--settings PATH]
#   install_issue_hooks.sh --remove  [--settings PATH]
#   install_issue_hooks.sh --help

set -euo pipefail

err() { echo "install-issue-hooks: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SCRIPT="${SCRIPT_DIR}/issue_support_hook.sh"
CONFIG_FILE="${ISSUE_HOOKS_CONFIG:-${SCRIPT_DIR}/../config/command_config.yml}"
SETTINGS_FILE="${ISSUE_HOOKS_SETTINGS:-${HOME}/.claude/settings.json}"
NATIVE_BEGIN="# >>> issue-support >>>"
NATIVE_END="# <<< issue-support <<<"

usage() {
    cat <<'USAGE'
Usage: install_issue_hooks.sh <--enable [--native] | --remove> [--settings PATH]

  --enable      Turn on the hooks (PostToolUse) and flip the runtime gate on
  --native      Also install a guarded git post-commit hook (commit-only)
  --remove      Remove both hook surfaces and flip the runtime gate off
  --settings P  Target Claude settings JSON (default: ~/.claude/settings.json)
USAGE
}

# set_enabled <skill> <true|false> — flip tool_policies.<skill>.enabled, keep comments
set_enabled() {
    local skill="$1" val="$2"
    [[ -f "${CONFIG_FILE}" ]] || { err "config not found: ${CONFIG_FILE}"; return 1; }
    python3 - "${CONFIG_FILE}" "${skill}" "${val}" <<'PY'
import sys, re
path, skill, val = sys.argv[1:4]
lines = open(path).read().splitlines(keepends=True)
out, inblk = [], False
for ln in lines:
    if re.match(r'^  %s:\s*$' % re.escape(skill), ln):
        inblk = True; out.append(ln); continue
    if inblk and re.match(r'^  \S', ln):
        inblk = False
    if inblk and re.match(r'^    enabled:', ln):
        ln = re.sub(r'(enabled:\s*)(true|false)', lambda m: m.group(1) + val, ln)
    out.append(ln)
open(path, 'w').write(''.join(out))
PY
}

# merge_settings <add|remove> — idempotently add/remove the PostToolUse entry
merge_settings() {
    local action="$1"
    mkdir -p "$(dirname "${SETTINGS_FILE}")"
    [[ -f "${SETTINGS_FILE}" ]] || echo '{}' >"${SETTINGS_FILE}"
    python3 - "${SETTINGS_FILE}" "${action}" "${HOOK_SCRIPT}" <<'PY'
import sys, json
path, action, cmd = sys.argv[1:4]
try:
    data = json.load(open(path)) or {}
except Exception:
    data = {}
hooks = data.setdefault("hooks", {})
arr = hooks.setdefault("PostToolUse", [])
# Filter at the HOOK level so sibling hooks co-located under the same matcher
# entry are preserved; drop an entry only once its hooks list becomes empty.
for e in arr:
    e["hooks"] = [h for h in e.get("hooks", []) if h.get("command") != cmd]
arr = [e for e in arr if e.get("hooks")]
if action == "add":
    arr.append({"matcher": "Bash",
                "hooks": [{"type": "command", "command": cmd, "timeout": 30}]})
hooks["PostToolUse"] = arr
json.dump(data, open(path, "w"), indent=2)
PY
}

install_native() {
    local hooks_dir post
    hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null || true)"
    [[ -n "${hooks_dir}" ]] || { err "not a git repo; skipping --native"; return 0; }
    mkdir -p "${hooks_dir}"
    post="${hooks_dir}/post-commit"
    if [[ -f "${post}" ]] && ! grep -qF "${NATIVE_BEGIN}" "${post}"; then
        err "existing post-commit hook found; refusing to clobber (merge manually)"
        return 0
    fi
    if [[ -f "${post}" ]] && grep -qF "${NATIVE_BEGIN}" "${post}"; then
        return 0   # already managed (idempotent)
    fi
    local had_file=0
    [[ -f "${post}" ]] && had_file=1
    # Keep the shebang INSIDE the managed block when we create the file, so that
    # remove_native strips the entire managed contribution atomically (bug_007).
    {
        echo "${NATIVE_BEGIN}"
        [[ "${had_file}" == "1" ]] || echo '#!/usr/bin/env bash'
        echo "\"${SCRIPT_DIR}/issue_support.sh\" sync-commit HEAD || true"
        echo "${NATIVE_END}"
    } >>"${post}"
    chmod +x "${post}"
}

remove_native() {
    local hooks_dir post tmp
    hooks_dir="$(git rev-parse --git-path hooks 2>/dev/null || true)"
    [[ -n "${hooks_dir}" ]] || return 0
    post="${hooks_dir}/post-commit"
    [[ -f "${post}" ]] || return 0
    grep -qF "${NATIVE_BEGIN}" "${post}" || return 0
    tmp="$(mktemp)"
    awk -v b="${NATIVE_BEGIN}" -v e="${NATIVE_END}" '
        $0==b{skip=1; next} $0==e{skip=0; next} !skip{print}' "${post}" >"${tmp}"
    mv "${tmp}" "${post}"
    # If nothing but a shebang (or nothing) remains, we created this file — unlink
    # it so a later --enable --native is not blocked by its own residual (bug_007).
    if [[ ! -s "${post}" ]] || ! grep -qvE '^#!' "${post}"; then
        rm -f "${post}"
    else
        chmod +x "${post}"
    fi
}

# --- arg parsing ------------------------------------------------------------
ACTION="" NATIVE=0
[[ $# -eq 0 ]] && { usage >&2; exit 1; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --enable) ACTION="enable"; shift ;;
        --remove) ACTION="remove"; shift ;;
        --native) NATIVE=1; shift ;;
        --settings) SETTINGS_FILE="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) err "unknown option: $1"; usage >&2; exit 1 ;;
    esac
done

case "${ACTION}" in
    enable)
        set_enabled pr-issue-sync true
        set_enabled commit-issue-sync true
        merge_settings add
        [[ "${NATIVE}" == "1" ]] && install_native
        echo "issue-linking hooks enabled (settings: ${SETTINGS_FILE})"
        ;;
    remove)
        set_enabled pr-issue-sync false
        set_enabled commit-issue-sync false
        merge_settings remove
        remove_native
        echo "issue-linking hooks removed/disabled"
        ;;
    *) err "specify --enable or --remove"; usage >&2; exit 1 ;;
esac
