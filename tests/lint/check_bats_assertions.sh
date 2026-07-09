#!/usr/bin/env bash
# check_bats_assertions.sh — flag non-final bare [[ ]] assertions in bats
# tests, which SILENTLY PASS under macOS Bash 3.2 + bats (issue #479).
#
# Repro (bash 3.2.57 + bats 1.13.0): this test passes despite the failing
# assertion, because the non-final [[ ]] failure is swallowed by errexit
# handling; the same test on Linux/bash 5 fails — so local RED runs can lie
# while CI stays honest:
#   @test "should fail but passes" { out="x"; [[ "$out" == "y" ]]; echo after; }
#
# Rule: in any *.bats file, a whole-line bare `[[ ... ]]` (no ||/&&, trailing
# comment allowed) whose next non-empty line is not the closing `}` of the test
# is flagged, UNLESS its inline comment contains `assertion-safe`. Fix by
# chaining `|| return 1` or moving the assertion to final position.
#
# Output: one `file:line` per finding; exit 1 if any, else 0.
# Usage: check_bats_assertions.sh [file.bats ...]   (no args = all tracked *.bats)
set -euo pipefail

err() { echo -e "\033[0;31mcheck-bats-assertions: $*\033[0m" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

files=()
if [[ $# -gt 0 ]]; then
    files=("$@")
else
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    cd "$repo_root"
    while IFS= read -r f; do
        # Skip our own test file: its heredoc fixtures quote the unsafe pattern.
        [[ "$f" == tests/bats/check_bats_assertions.bats ]] && continue
        files+=("$f")
    done < <(git ls-files '*.bats')
fi

# scan_file FILE -> prints findings (one "file:line" per line).
scan_file() {
    local f="$1" lines=() line stripped code comment next i j n
    # Split a bare whole-line [[ ]] into code and optional trailing comment,
    # so `[[ ... ]]  # note` is still seen as an assertion and only the
    # comment (not the mere presence of one) can opt out.
    local code_re='^(\[\[ .+ \]\])[[:space:]]*(#.*)?$'
    while IFS= read -r line || [[ -n "$line" ]]; do
        lines+=("$line")
    done < "$f"
    n=${#lines[@]}
    for ((i = 0; i < n; i++)); do
        stripped="${lines[$i]#"${lines[$i]%%[![:space:]]*}"}"
        [[ "$stripped" =~ $code_re ]] || continue
        code="${BASH_REMATCH[1]}"
        comment="${BASH_REMATCH[2]:-}"
        [[ "$code" == *"||"* || "$code" == *"&&"* ]] && continue
        [[ "$comment" == *"assertion-safe"* ]] && continue
        # Non-final: next non-empty line is not the test's closing brace.
        for ((j = i + 1; j < n; j++)); do
            next="${lines[$j]#"${lines[$j]%%[![:space:]]*}"}"
            [[ -z "$next" ]] && continue
            [[ "$next" != "}" ]] && echo "$f:$((i + 1))"
            break
        done
    done
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
    err "$count non-final bare [[ ]] assertion(s) — these SILENTLY PASS on macOS Bash 3.2."
    err "Chain with '|| return 1', move to final position, or append '# assertion-safe'."
    exit 1
fi
exit 0
