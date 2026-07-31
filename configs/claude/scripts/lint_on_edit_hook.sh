#!/usr/bin/env bash
# lint_on_edit_hook.sh - PostToolUse adapter: advisory language linting on edit.
#
# Reads the Claude Code PostToolUse JSON payload on stdin, extracts the edited
# file path, and runs the language-appropriate linter for a small set of file
# types. Advisory ONLY: it never blocks (always exits 0), never auto-fixes, and
# fails open when a linter is not installed. Findings are written to stderr.
#
# Dispatch:  .sh→shellcheck  .py→ruff  .yml/.yaml→yamllint
#            .json→python3 json.load  .md/.mdc→markdownlint
#            .md→docs_lint.py line caps (only where the repo ships doc_limits.yml)
#
# Wire via settings.local.json:
#   "hooks": { "PostToolUse": [ { "matcher": "Write|Edit",
#     "hooks": [ { "type": "command",
#       "command": "~/.claude/scripts/lint_on_edit_hook.sh" } ] } ] }
#
# Design constraints (feature 366; contracts/edit-time-hook.md):
#   - set -uo pipefail, NOT -e: must survive a linter's non-zero exit.
#   - always exit 0; never mutate the file; fail open on missing tools.
#   - each linter is time-bounded (timeout/gtimeout when available).
#   - macOS Bash 3.2 safe.

set -uo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "lint_on_edit_hook.sh: $*" >&2; else printf '%s\n' "lint_on_edit_hook.sh: $*" >&2; fi; }

usage() {
    cat << 'EOF'
lint_on_edit_hook.sh - advisory PostToolUse linter (Write|Edit)

Reads the Claude Code PostToolUse JSON payload on stdin, extracts the edited
file path, and runs a language-appropriate linter. Advisory only: always
exits 0, never auto-fixes, fails open on missing tools.

Dispatch: .sh→shellcheck  .py→ruff  .yml/.yaml→yamllint
          .json→json.load  .md/.mdc→markdownlint
          .md→docs_lint.py caps (repos shipping doc_limits.yml)

Usage: lint_on_edit_hook.sh [--help]
EOF
}

case "${1:-}" in
    -h | --help)
        usage
        exit 0
        ;;
esac

# Run a command with an upper time bound. Prefer timeout/gtimeout; otherwise run
# directly (linters on a single file are fast — direct is an acceptable fallback).
_run() {
    local secs="$1"
    shift
    if command -v timeout > /dev/null 2>&1; then
        timeout "$secs" "$@"
    elif command -v gtimeout > /dev/null 2>&1; then
        gtimeout "$secs" "$@"
    elif command -v perl > /dev/null 2>&1; then
        # No timeout binary (e.g. stock macOS without coreutils): perl's alarm
        # survives exec and hard-kills the linter after $secs (exit 142 on
        # SIGALRM), preserving the linter's stdout/stderr for the caller.
        perl -e 'alarm shift; exec @ARGV or exit 127' "$secs" "$@"
    else
        "$@"
    fi
}

# Run a linter on the edited file IF it is installed; emit any output to stderr.
# Never returns non-zero to the caller (advisory). 124 (timeout) / 142 (perl
# SIGALRM) are surfaced as an advisory note so a timed-out lint is observable.
report() {
    local tool="$1"
    shift
    command -v "$tool" > /dev/null 2>&1 || return 0
    local out rc=0
    out="$(_run 8 "$tool" "$@" 2>&1)" || rc=$?
    if [[ "$rc" -eq 124 || "$rc" -eq 142 ]]; then
        err "$tool timed out on $FILE (>8s); skipped"
    elif [[ -n "$out" ]]; then
        printf 'lint-on-edit: %s:\n%s\n' "$FILE" "$out" >&2
    fi
    return 0
}

# Extract the edited file path from the PostToolUse payload (empty if absent).
# Prefer .tool_input.file_path, fall back to a top-level .file_path — payload
# shape varies across Claude Code versions (mirrors version_pin_hook.sh).
FILE="$(python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
ti = d.get("tool_input") or {}
print(ti.get("file_path") or d.get("file_path") or "")' 2> /dev/null || true)"

[[ -n "$FILE" && -f "$FILE" ]] || exit 0

# Skip generated / vendored / scaffold paths (substring match on the path).
case "$FILE" in
    */.Jules/* | */node_modules/* | */.git/* | */templates/scaffold/*)
        exit 0
        ;;
esac

# Lowercase the extension for dispatch.
ext="${FILE##*.}"
ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"

# Locate repo config (.markdownlint.jsonc) via the file's git toplevel, if any.
repo_root="$(git -C "$(dirname "$FILE")" rev-parse --show-toplevel 2> /dev/null || true)"

case "$ext" in
    sh | bash)
        # Advisory edit-time uses --severity=info (catches correctness issues like
        # SC2086 unquoted vars); the commit/CI gate stays at --severity=warning.
        report shellcheck --severity=info "$FILE"
        ;;
    py)
        # ruff auto-discovers the nearest pyproject.toml; --no-fix keeps it
        # read-only (advisory; guarantee G2 — never mutates the file).
        report ruff check --no-fix "$FILE"
        ;;
    yml | yaml)
        report yamllint -f parsable "$FILE"
        ;;
    json)
        if command -v python3 > /dev/null 2>&1; then
            json_out="$(_run 8 python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$FILE" 2>&1)" || true
            [[ -n "$json_out" ]] && printf 'lint-on-edit: %s:\n%s\n' "$FILE" "$json_out" >&2
        fi
        ;;
    md | mdc)
        if [[ -n "$repo_root" && -f "$repo_root/.markdownlint.jsonc" ]]; then
            report markdownlint -c "$repo_root/.markdownlint.jsonc" "$FILE"
        else
            report markdownlint "$FILE"
        fi
        # Line-cap check, opt-in per repo: only runs where the repo ships a
        # doc_limits.yml, so editing a .md in an unrelated project never nags
        # about caps that project never adopted. Reports ONLY when over cap —
        # docs_lint.py always prints a summary, and an advisory that fires on
        # every write is one people stop reading. Cursor .mdc rules are
        # generated, so they are excluded.
        if [[ "$ext" == "md" && -n "$repo_root" ]]; then
            doc_limits=""
            for candidate in \
                "$repo_root/configs/claude/config/doc_limits.yml" \
                "$repo_root/.doc-limits.yml"; do
                [[ -f "$candidate" ]] && doc_limits="$candidate" && break
            done
            docs_lint="$(dirname "${BASH_SOURCE[0]}")/docs_lint.py"
            if [[ -n "$doc_limits" && -f "$docs_lint" ]] && command -v python3 > /dev/null 2>&1; then
                cap_out=""
                if ! cap_out="$(cd "$repo_root" && _run 8 python3 "$docs_lint" \
                    --limits "$doc_limits" "$FILE" 2>&1)"; then
                    printf 'lint-on-edit: %s:\n%s\n' "$FILE" "$cap_out" >&2
                fi
            fi
        fi
        ;;
    *)
        : # unknown extension — no-op
        ;;
esac

# Code Constitution (CON-*) — structural findings the language linters do not
# look for: size ceilings, duplicated blocks, embedded data payloads, swallowed
# errors. Advisory like everything else here, and ratcheted against the recorded
# baseline so an edit to a legacy file reports only what this edit added.
constitution_check="$(dirname "${BASH_SOURCE[0]}")/constitution_check.py"
if [[ -f "$constitution_check" ]] && command -v python3 > /dev/null 2>&1; then
    con_out=""
    if ! con_out="$(_run 10 python3 "$constitution_check" "$FILE" 2>&1)"; then
        [[ -n "$con_out" ]] && printf 'constitution: %s\n' "$con_out" >&2
    fi
fi

exit 0
