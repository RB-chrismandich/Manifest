#!/usr/bin/env bash
set -uo pipefail

usage() {
    cat << 'EOF'
Usage: run_pr_regression.sh [--quick] [--help]

Runs repository-local, offline regression gates. Exit 0=PASS, 1=WARN, 2=FAIL.
EOF
}

QUICK=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick) QUICK=1 ;;
        --help | -h)
            usage
            exit 0
            ;;
        *)
            echo "pr-smoke: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if ! git rev-parse --show-toplevel > /dev/null 2>&1; then
    echo "pr-smoke: run from a git repository" >&2
    exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT" || exit 2

FAILURES=0
WARNINGS=0

run_gate() {
    local name="$1"
    shift
    if "$@"; then
        printf '| %s | PASS |\n' "$name"
    else
        printf '| %s | FAIL |\n' "$name"
        FAILURES=$((FAILURES + 1))
    fi
}

optional_gate() {
    local name="$1" binary="$2"
    shift 2
    if ! command -v "$binary" > /dev/null 2>&1; then
        printf '| %s | WARN (missing %s) |\n' "$name" "$binary"
        WARNINGS=$((WARNINGS + 1))
        return
    fi
    run_gate "$name" "$@"
}

echo '| Gate | Result |'
echo '|---|---|'
run_gate 'git diff check' git diff --check

if [[ -d tests/python ]]; then
    optional_gate 'python tests' python3 python3 -m pytest tests/python -q
fi
if [[ -d tests/bats ]]; then
    optional_gate 'bats tests' bats bats tests/bats
fi
if [[ "$QUICK" -eq 0 && -f pyproject.toml ]] && command -v uv > /dev/null 2>&1; then
    run_gate 'generated views' uv run python tools/generate_plugin_views.py --check
fi

if [[ "$FAILURES" -gt 0 ]]; then
    echo "Verdict: FAIL ($FAILURES failing gate(s))"
    exit 2
fi
if [[ "$WARNINGS" -gt 0 ]]; then
    echo "Verdict: WARN ($WARNINGS unavailable optional gate(s))"
    exit 1
fi
echo 'Verdict: PASS'
