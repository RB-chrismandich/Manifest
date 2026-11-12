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

# Discover Manifest's optional project-local tools without binding this bundle to
# a deployed home or a fixed source-tree path.
manifest_generator="$(git ls-files -- '*/generate_commands_doc.py' | head -n 1)"
manifest_scripts_dir=""
if [[ -n "$manifest_generator" ]]; then
    manifest_scripts_dir="${manifest_generator%/generate_commands_doc.py}"
fi

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

# Repository-local scripts exist only in some targets (e.g. Manifest itself);
# absence is a WARN, but a present script that fails is still a FAIL.
local_script_gate() {
    local name="$1" script="$2"
    if [[ ! -e "$script" ]]; then
        printf '| %s | WARN (missing %s) |\n' "$name" "$script"
        WARNINGS=$((WARNINGS + 1))
        return
    fi
    run_gate "$name" "${@:2}"
}

# Run pytest from the repository root so its own rootdir/config discovery
# (testpaths, tests/, tests/python/, ...) decides the suite. Exit 5 means no
# tests were collected; every other nonzero status is a real failure.
python_gate() {
    local name='python tests' status
    if ! command -v python3 > /dev/null 2>&1; then
        printf '| %s | WARN (missing python3) |\n' "$name"
        WARNINGS=$((WARNINGS + 1))
        return
    fi
    python3 -m pytest -q
    status=$?
    case "$status" in
        0) printf '| %s | PASS |\n' "$name" ;;
        5)
            printf '| %s | WARN (no Python tests collected) |\n' "$name"
            WARNINGS=$((WARNINGS + 1))
            ;;
        *)
            printf '| %s | FAIL |\n' "$name"
            FAILURES=$((FAILURES + 1))
            ;;
    esac
}

echo '| Gate | Result |'
echo '|---|---|'
run_gate 'git diff check' git diff --check

if [[ "$QUICK" -eq 0 ]]; then
    if [[ -n "$manifest_scripts_dir" ]]; then
        optional_gate 'ShellCheck Manifest scripts' shellcheck \
            shellcheck -S warning "$manifest_scripts_dir"/*.sh
    fi
    local_script_gate 'empty-array expansion lint' tests/lint/check_array_expansion.sh
    local_script_gate 'Bats assertion lint' tests/lint/check_bats_assertions.sh
    optional_gate 'Markdown lint' markdownlint-cli2 \
        markdownlint-cli2 AGENTS.md CLAUDE.md README.md docs/*.md
    if [[ -n "$manifest_scripts_dir" ]]; then
        run_gate 'command guide drift' "$manifest_scripts_dir/generate_commands_doc.py" --check
        run_gate 'shell syntax' bash -n "$manifest_scripts_dir"/*.sh
    fi
fi

if [[ "$QUICK" -eq 0 ]]; then
    python_gate
fi
if [[ "$QUICK" -eq 0 && -d tests/bats ]]; then
    optional_gate 'bats tests' bats bats tests/bats/
fi
if [[ "$FAILURES" -gt 0 ]]; then
    echo "Verdict: FAIL ($FAILURES failing gate(s))"
    exit 2
fi
if [[ "$WARNINGS" -gt 0 ]]; then
    echo "Verdict: WARN ($WARNINGS warning gate(s))"
    exit 1
fi
echo 'Verdict: PASS'
