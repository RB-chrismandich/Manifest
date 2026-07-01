#!/usr/bin/env bash
# check_array_expansion.sh — flag empty-array expansions unsafe under
# macOS Bash 3.2 + `set -u` (specs/003 FR-011, contracts/array-guard.md).
#
# Rule: in any *.sh file, an expansion "${name[@]}" or "${name[*]}" is flagged  # array-safe
# when the SAME file initializes that array as `name=()` (i.e. it can be empty
# at expansion time), UNLESS:
#   - the expansion uses the guard idiom  "${name[@]+"${name[@]}"}"   , or
#   - the line carries an inline `# array-safe` opt-out comment.
#
# Output: one `file:line: name` per finding; exit 1 if any, else 0.
# Usage: check_array_expansion.sh [file.sh ...]   (no args = all tracked *.sh)
set -euo pipefail

err() { echo "check-array-expansion: $*" >&2; }

files=()
if [[ $# -gt 0 ]]; then
    files=("$@")
else
    # All tracked shell scripts (repo root = two levels up from tests/lint/).
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    cd "$repo_root"
    # .specify/ is vendored speckit tooling (set -e only, no -u; expansions
    # length-guarded there) — out of scope; we lint the code we own.
    while IFS= read -r f; do
        [[ "$f" == .specify/* ]] && continue
        # Skip self: the rule documentation above quotes the unsafe pattern.
        [[ "$f" == tests/lint/check_array_expansion.sh ]] && continue
        files+=("$f")
    done < <(git ls-files '*.sh')
fi

# scan_file FILE -> prints findings (one "file:line: name" per line).
scan_file() {
    local f="$1" empties name hit line_no line
    empties=$(grep -oE '[A-Za-z_][A-Za-z0-9_]*=\([[:space:]]*\)' "$f" 2> /dev/null |
        sed -E 's/=\([[:space:]]*\)$//' | sort -u || true)
    [[ -z "$empties" ]] && return 0
    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        while IFS= read -r hit; do
            [[ -z "$hit" ]] && continue
            line_no="${hit%%:*}"
            line="${hit#*:}"
            # Guarded idiom and explicit opt-outs are fine.
            [[ "$line" == *"\${${name}[@]+"* || "$line" == *"\${${name}[*]+"* ||
                "$line" == *"\${${name}[@]:+"* || "$line" == *"\${${name}[*]:+"* ]] && continue
            [[ "$line" == *"# array-safe"* ]] && continue
            echo "$f:$line_no: $name"
        done <<< "$(grep -nE "\\\$\{${name}\[[@*]\]\}" "$f" 2> /dev/null || true)"
    done <<< "$empties"
    return 0
}

findings=""
for f in "${files[@]+"${files[@]}"}"; do
    [[ -f "$f" ]] || continue
    out="$(scan_file "$f")"
    [[ -n "$out" ]] && findings+="${out}"$'\n'
done

findings="$(printf '%s' "$findings" | sort -u)"
if [[ -n "$findings" ]]; then
    echo "$findings"
    count=$(printf '%s\n' "$findings" | wc -l | tr -d ' ')
    err "$count unsafe empty-array expansion(s) under set -u (Bash 3.2)."
    err "Fix with \"\${arr[@]+\"\${arr[@]}\"}\" or append '# array-safe' if provably non-empty."
    exit 1
fi
exit 0
