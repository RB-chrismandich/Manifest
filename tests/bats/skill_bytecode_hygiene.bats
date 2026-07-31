#!/usr/bin/env bats
# Guard: .apm/skills/ must hold ZERO compiled-bytecode artifacts (R4).
#
# Why this is not merely untidy: ~/.claude/skills is owned by apm, and apm
# declines to adopt a directory containing files it did not place. A single
# __pycache__/ under a skill makes apm silently skip that whole skill on
# deploy ("[!] 1 file skipped"), leaving an unowned orphan in the home tree —
# exactly what configs/claude/scripts/apm_ownership_report.sh was written to
# catch after ai-hooks-integration hit it.
#
# Bytecode is gitignored, so CI stays green and `git status` stays clean while
# the deployed side rots. Nothing else in the suite looks at the working tree
# for it, which is why this check exists at all.
#
# The writer was `pytest .apm/skills/ai-hooks-integration/tests/`: pytest's
# assertion rewriter caches a .pyc per test module, and importing the runtime
# under test caches one per imported module. Suppression lives in the repo-root
# conftest.py (sys.dont_write_bytecode), which every pytest invocation loads —
# CI, the pr-smoke mirror, and a bare `python3 -m pytest` alike. That is the
# same "kill it at the Python entry point" fix as the `-B` at the hook spawn
# sites in install_all.py / runtime/unified_hook.py.
#
# If this fails: delete the artifacts (`find .apm/skills \( -name __pycache__
# -o -name '*.pyc' \) -exec rm -rf {} +`) and find what wrote them — a new
# Python entry point that needs -B / sys.dont_write_bytecode, not a new
# exclusion here.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SKILLS_DIR="$REPO_ROOT/.apm/skills"
CONFTEST="$REPO_ROOT/conftest.py"

# Emit every bytecode artifact under $1, one path per line (empty = clean).
# Kept as a function so the planted-fixture test below exercises the SAME
# detector the real-tree test uses; a detector proven only against a clean
# tree is indistinguishable from `true`.
bytecode_artifacts() {
    local root="$1"
    [ -d "$root" ] || return 0
    find "$root" \( -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' \) -print
}

@test "skills tree carries no __pycache__ or .pyc (apm will not adopt them)" {
    local found
    found="$(bytecode_artifacts "$SKILLS_DIR")"
    if [ -n "$found" ]; then
        echo "Compiled bytecode under .apm/skills/ — apm will skip these skills:" >&2
        printf '%s\n' "$found" >&2
        return 1
    fi
}

@test "detector flags a planted __pycache__ and a loose .pyc" {
    local tmp found
    tmp="$(mktemp -d "${BATS_TMPDIR:-/tmp}/skill_bytecode.XXXXXX")"
    mkdir -p "$tmp/some-skill/scripts/__pycache__"
    : > "$tmp/some-skill/scripts/__pycache__/mod.cpython-314.pyc"
    : > "$tmp/some-skill/stray.pyc"

    found="$(bytecode_artifacts "$tmp")"
    rm -rf "$tmp"

    if ! printf '%s\n' "$found" | grep -q '__pycache__$'; then
        echo "detector missed a planted __pycache__ directory: $found" >&2
        return 1
    fi
    if ! printf '%s\n' "$found" | grep -q 'stray\.pyc$'; then
        echo "detector missed a planted loose .pyc: $found" >&2
        return 1
    fi
}

@test "repo-root conftest.py suppresses bytecode for every pytest run" {
    [ -f "$CONFTEST" ] || {
        echo "missing $CONFTEST — the mechanism that keeps .apm/skills clean" >&2
        return 1
    }
    # Behavioural, not a grep: import it and read the flag it is supposed to
    # set. -B so this probe cannot itself write the bytecode it guards against.
    run python3 -B -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
import conftest  # noqa: F401
print('dont_write_bytecode=%s' % sys.dont_write_bytecode)
"
    [ "$status" -eq 0 ] || {
        echo "importing conftest.py failed (exit $status): $output" >&2
        return 1
    }
    if [ "$output" != "dont_write_bytecode=True" ]; then
        echo "conftest.py did not set sys.dont_write_bytecode: $output" >&2
        return 1
    fi
}

# Fail unless $SKILLS_DIR is bytecode-free right now. Guards the two runner
# tests below from reporting someone else's mess as their own.
require_clean_tree() {
    local dirty
    dirty="$(bytecode_artifacts "$SKILLS_DIR")"
    [ -z "$dirty" ] && return 0
    echo "tree already dirty before this test ran: $dirty" >&2
    return 1
}

@test "running the skill's entry points directly writes no bytecode" {
    # The conftest.py above only reaches processes pytest starts. The suite also
    # spawns these scripts as child interpreters (and so does a real hook fire),
    # and a child that imports runtime/ caches a .pyc next to it. Plain python3,
    # no -B and no inherited PYTHONDONTWRITEBYTECODE: each script must suppress
    # this itself. Needs no pytest, so it runs everywhere bats does.
    require_clean_tree || return 1

    local script
    for script in \
        "scripts/runtime/unified_hook.py" \
        "scripts/merge_hooks.py" \
        "scripts/remove_hooks.py" \
        "scripts/install_cli_wrapper.py"; do
        run env -u PYTHONDONTWRITEBYTECODE \
            python3 "$SKILLS_DIR/ai-hooks-integration/$script" --help
        [ "$status" -eq 0 ] || {
            echo "$script --help exited $status: $output" >&2
            return 1
        }
    done

    local after
    after="$(bytecode_artifacts "$SKILLS_DIR")"
    if [ -n "$after" ]; then
        echo "running the skill's entry points wrote bytecode into .apm/skills/:" >&2
        printf '%s\n' "$after" >&2
        echo "add 'sys.dont_write_bytecode = True' to the entry point that imports runtime/." >&2
        return 1
    fi
}

@test "running the ai-hooks-integration suite writes no bytecode" {
    if ! python3 -c 'import pytest' 2> /dev/null; then
        skip "pytest not installed (the tree and entry-point checks still gate this)"
    fi
    require_clean_tree || return 1

    # The literal reproduction: the invocation from ci.yml and the pr-smoke
    # mirror, with no -B and no PYTHONDONTWRITEBYTECODE to lean on.
    run env -u PYTHONDONTWRITEBYTECODE \
        python3 -m pytest "$SKILLS_DIR/ai-hooks-integration/tests/" -q
    [ "$status" -eq 0 ] || {
        echo "ai-hooks suite failed (exit $status): $output" >&2
        return 1
    }

    local after
    after="$(bytecode_artifacts "$SKILLS_DIR")"
    if [ -n "$after" ]; then
        echo "the test suite wrote bytecode into .apm/skills/:" >&2
        printf '%s\n' "$after" >&2
        return 1
    fi
}
