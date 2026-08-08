#!/usr/bin/env bash
# audit_log.sh — append-only JSONL audit writer for /issue-dev-auto
#
# Subcommands:
#   append <json>   Redact known secret patterns and append record; exit 0 (fail-open)
#   redact <text>   Emit redacted version of text on stdout; exit 0
#
# Env: AUDIT_LOG_FILE (generic target, preferred — lets other features, e.g.
#      CDDL, write their own per-tool audit files through this writer) or
#      AUTO_ISSUE_DEV_AUDIT_FILE (legacy override)

set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "audit-log: $*" >&2; else printf '%s\n' "audit-log: $*" >&2; fi; }

FORGE_RUNTIME_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
FORGE_CONFIG_DIR="$FORGE_RUNTIME_DIR/config"
FORGE_STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/manifest/forge"
export FORGE_RUNTIME_DIR FORGE_CONFIG_DIR FORGE_STATE_DIR
AUDIT_FILE="${AUDIT_LOG_FILE:-${AUTO_ISSUE_DEV_AUDIT_FILE:-${FORGE_STATE_DIR}/audit.jsonl}}"

REDACT_PY='
import sys, re
text = sys.argv[1] if len(sys.argv) > 1 else ""
PATTERNS = [
    (r"(ghp|gho|github_pat)_[A-Za-z0-9_]{20,}", "<REDACTED:github-token>"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}",              "<REDACTED:anthropic-key>"),
    (r"sk-[A-Za-z0-9_-]{20,}",                   "<REDACTED:api-key>"),
    (r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+", r"\1=<REDACTED>"),
    (r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*",     "Bearer <REDACTED>"),
]
for pat, repl in PATTERNS:
    text = re.sub(pat, repl, text)
sys.stdout.write(text)
'

usage() {
    cat << 'USAGE'
Usage: audit_log.sh <subcommand> [args]

  append <json>   Redact and append one record to the audit log; exit 0 (fail-open)
  redact <text>   Emit redacted version of text on stdout; exit 0

Env: AUDIT_LOG_FILE (preferred) or AUTO_ISSUE_DEV_AUDIT_FILE (legacy).
     Default: $XDG_STATE_HOME/manifest/forge/audit.jsonl
USAGE
}

cmd_redact() {
    python3 -c "${REDACT_PY}" "${1:-}"
}

cmd_append() {
    local record="${1:-}"
    [[ -n "${record}" ]] || {
        err "append: record required"
        return 0
    }
    local redacted
    if ! redacted="$(cmd_redact "${record}" 2> /dev/null)"; then
        err "WARNING: redaction failed; skipping audit append to prevent secret leak"
        return 0
    fi
    local dir
    dir="$(dirname "${AUDIT_FILE}")"
    mkdir -p "${dir}" 2> /dev/null || true
    printf '%s\n' "${redacted}" >> "${AUDIT_FILE}" 2> /dev/null ||
        err "WARNING: could not append to ${AUDIT_FILE} (audit record lost)"
    return 0
}

main() {
    local sub="${1:-}"
    shift || true
    case "${sub}" in
        --help | -h | help)
            usage
            exit 0
            ;;
        append)
            cmd_append "$@"
            exit 0
            ;;
        redact)
            cmd_redact "$@"
            exit 0
            ;;
        *)
            err "unknown subcommand: ${sub:-<none>}"
            usage >&2
            exit 64
            ;;
    esac
}

main "$@"
