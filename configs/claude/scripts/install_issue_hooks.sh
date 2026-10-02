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

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "install-issue-hooks: $*" >&2; else printf '%s\n' "install-issue-hooks: $*" >&2; fi; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SCRIPT="${SCRIPT_DIR}/issue_support_hook.sh"
# NOTE: this script no longer reads or writes command_config.yml at all.
# The opt-in moved to the user-scope overlay below (T051/FR-034), so the
# former CONFIG_FILE variable was removed rather than left dangling —
# having no path to the package config IS the guarantee.
# T051/FR-034: the opt-in is written to a user-scope overlay that no package
# owns, NOT to the deployed command_config.yml. Writing a deployed file made the
# opt-in a piece of state living inside a build artifact, which any deploy is
# free to overwrite -- the whole reason preserve_issue_sync_gates() exists. The
# fix is to stop writing there, not to carry the write across harder.
ISSUE_HOOKS_STATE="${ISSUE_HOOKS_STATE:-${HOME}/.manifest/issue_hooks.yml}"
SETTINGS_FILE="${ISSUE_HOOKS_SETTINGS:-${HOME}/.claude/settings.json}"
NATIVE_BEGIN="# >>> issue-support >>>"
NATIVE_END="# <<< issue-support <<<"

usage() {
    cat << 'USAGE'
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
    mkdir -p "$(dirname "${ISSUE_HOOKS_STATE}")"
    python3 - "${ISSUE_HOOKS_STATE}" "${skill}" "${val}" << 'ST'
import sys, os, yaml
path, skill, val = sys.argv[1:4]
data = {}
if os.path.exists(path):
    try:
        data = yaml.safe_load(open(path)) or {}
    except Exception:
        # A corrupted overlay must not silently discard the user's other opt-ins
        # by being overwritten wholesale.
        sys.stderr.write(f"install-issue-hooks: {path} is unreadable; refusing to overwrite it\n")
        sys.exit(1)
policies = data.setdefault("tool_policies", {})
policies.setdefault(skill, {})["enabled"] = (val == "true")
header = (
    "# User-scope opt-in state for the issue-sync hooks (T051/FR-034).\n"
    "# Written by install_issue_hooks.sh; owned by you, not by any package, so\n"
    "# no deploy overwrites it. Takes precedence over the deployed\n"
    "# command_config.yml, which remains the default source for everything else.\n"
)
with open(path, "w") as f:
    f.write(header)
    yaml.safe_dump(data, f, default_flow_style=False, sort_keys=True)
ST
}

# merge_settings <add|remove> — idempotently add/remove the PostToolUse entry
merge_settings() {
    local action="$1"
    mkdir -p "$(dirname "${SETTINGS_FILE}")"
    [[ -f "${SETTINGS_FILE}" ]] || echo '{}' > "${SETTINGS_FILE}"
    python3 - "${SETTINGS_FILE}" "${action}" "${HOOK_SCRIPT}" << 'PY'
import sys, json
path, action, cmd = sys.argv[1:4]
try:
    data = json.load(open(path)) or {}
except Exception:
    data = {}
import os
hooks = data.setdefault("hooks", {})
arr = hooks.setdefault("PostToolUse", [])


def _same_hook(existing, wanted):
    """Match on the script NAME appearing anywhere in the command.

    HOOK_SCRIPT is derived from wherever this installer was invoked, so the
    same hook registers under different absolute paths when run from a repo
    clone versus the deployed ~/.claude/scripts copy. Comparing full strings
    made each path look like a distinct hook, so both survived and the hook
    fired twice on every matching tool call. Identity is the basename.

    Scan EVERY token, not just the first: hook commands are commonly
    interpreter-prefixed ("/usr/bin/env bash <path>", "python3 <path>
    --handler ...") — this repo's own PreToolUse entry has that shape. Keying
    on token[0] alone sees "env"/"python3" and misses the hook entirely, so a
    hand-written variant survives --enable (duplicate) and --remove (orphan).
    """
    if not existing:
        return False
    target = os.path.basename(wanted.split()[0])
    return any(os.path.basename(tok) == target for tok in existing.split())


# Filter at the HOOK level so sibling hooks co-located under the same matcher
# entry are preserved; drop an entry only once its hooks list becomes empty.
for e in arr:
    e["hooks"] = [
        h for h in e.get("hooks", []) if not _same_hook(h.get("command", ""), cmd)
    ]
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
    hooks_dir="$(git rev-parse --git-path hooks 2> /dev/null || true)"
    [[ -n "${hooks_dir}" ]] || {
        err "not a git repo; skipping --native"
        return 0
    }
    mkdir -p "${hooks_dir}"
    post="${hooks_dir}/post-commit"
    if [[ -f "${post}" ]] && ! grep -qF "${NATIVE_BEGIN}" "${post}"; then
        err "existing post-commit hook found; refusing to clobber (merge manually)"
        return 0
    fi
    if [[ -f "${post}" ]] && grep -qF "${NATIVE_BEGIN}" "${post}"; then
        return 0 # already managed (idempotent)
    fi
    local had_file=0
    [[ -f "${post}" ]] && had_file=1
    # Shebang must be the FIRST line so Git can exec the hook. When we create the
    # file it sits OUTSIDE the managed block; remove_native unlinks a shebang-only
    # residual afterwards, so the enable→remove→enable round-trip still works (bug_007).
    {
        [[ "${had_file}" == "1" ]] || echo '#!/usr/bin/env bash'
        echo "${NATIVE_BEGIN}"
        echo "\"${SCRIPT_DIR}/issue_support.sh\" sync-commit HEAD || true"
        echo "${NATIVE_END}"
    } >> "${post}"
    chmod +x "${post}"
}

remove_native() {
    local hooks_dir post tmp
    hooks_dir="$(git rev-parse --git-path hooks 2> /dev/null || true)"
    [[ -n "${hooks_dir}" ]] || return 0
    post="${hooks_dir}/post-commit"
    [[ -f "${post}" ]] || return 0
    grep -qF "${NATIVE_BEGIN}" "${post}" || return 0
    tmp="$(mktemp)"
    awk -v b="${NATIVE_BEGIN}" -v e="${NATIVE_END}" '
        $0==b{skip=1; next} $0==e{skip=0; next} !skip{print}' "${post}" > "${tmp}"
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
[[ $# -eq 0 ]] && {
    usage >&2
    exit 1
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --enable)
            ACTION="enable"
            shift
            ;;
        --remove)
            ACTION="remove"
            shift
            ;;
        --native)
            NATIVE=1
            shift
            ;;
        --settings)
            SETTINGS_FILE="$2"
            shift 2
            ;;
        --help | -h)
            usage
            exit 0
            ;;
        *)
            err "unknown option: $1"
            usage >&2
            exit 1
            ;;
    esac
done

case "${ACTION}" in
    enable)
        set_enabled issue-sync-pr true
        set_enabled issue-sync-commit true
        merge_settings add
        [[ "${NATIVE}" == "1" ]] && install_native
        echo "issue-linking hooks enabled (settings: ${SETTINGS_FILE})"
        ;;
    remove)
        set_enabled issue-sync-pr false
        set_enabled issue-sync-commit false
        merge_settings remove
        remove_native
        echo "issue-linking hooks removed/disabled"
        ;;
    *)
        err "specify --enable or --remove"
        usage >&2
        exit 1
        ;;
esac
