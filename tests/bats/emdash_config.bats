#!/usr/bin/env bats
# T009 (spec 483, US2) — `.emdash.json` config validity gate.
# Runs in CI via `bats tests/bats/` (the repo's config-validation surface).
# Enforces contracts/emdash-project-config.md:
#   Rule 1 — valid JSON.
#   Rule 2 — no tracked file in preservePatterns (esp. .claude/settings.local.json,
#            which IS tracked; listing it would corrupt worktrees / risk commits).

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
EMDASH_JSON="$REPO_ROOT/.emdash.json"

@test ".emdash.json exists at the repo root" {
    assert [ -f "$EMDASH_JSON" ]
}

@test ".emdash.json is valid JSON (contract Rule 1)" {
    run python3 -c "import json; json.load(open('$EMDASH_JSON'))"
    assert_success
}

@test ".emdash.json preservePatterns is an array" {
    run python3 -c "import json,sys; sys.exit(0 if isinstance(json.load(open('$EMDASH_JSON')).get('preservePatterns'), list) else 1)"
    assert_success
}

@test "preservePatterns contains no tracked file (contract Rule 2)" {
    # Each pattern must match only untracked/gitignored local config. A pattern
    # that resolves to a git-tracked path (via git ls-files pathspec/glob) means
    # emdash would overwrite committed content in a fresh worktree.
    local patterns
    patterns="$(python3 -c "import json; [print(p) for p in json.load(open('$EMDASH_JSON')).get('preservePatterns', [])]")"

    local offenders=""
    while IFS= read -r pat; do
        [ -z "$pat" ] && continue
        local matched
        matched="$(git -C "$REPO_ROOT" ls-files -- "$pat")"
        if [ -n "$matched" ]; then
            offenders="${offenders}
  pattern '$pat' matches tracked file(s):
$(echo "$matched" | sed 's/^/    /')"
        fi
    done <<< "$patterns"

    if [ -n "$offenders" ]; then
        echo "preservePatterns must list only untracked local config, but:$offenders" >&2
        return 1
    fi
}

@test "preservePatterns does not list .claude/settings.local.json (tracked, contract Rule 2)" {
    # Explicit guard: this file IS tracked and holds repo permissions; it must
    # never be a preserve target regardless of how the glob check evaluates.
    run python3 -c "import json,sys; pats=json.load(open('$EMDASH_JSON')).get('preservePatterns', []); sys.exit(1 if '.claude/settings.local.json' in pats else 0)"
    assert_success
}
