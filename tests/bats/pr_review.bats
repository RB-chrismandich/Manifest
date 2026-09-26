#!/usr/bin/env bats
# Tests for plugins/manifest-forge/runtime/bin/pr_review.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/plugins/manifest-forge/runtime/bin/pr_review.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/pr_review.XXXXXX")

    # Forge contract: no PR_REVIEW_FETCH seam — the script enumerates through
    # the native platform CLI on PATH. Stub `gh` to cat a fixture file that
    # uses the raw `gh pr list --json` shape (author.login, updatedAt,
    # mergeable MERGEABLE/CONFLICTING, isDraft, headRefName,
    # statusCheckRollup); the script normalizes it.
    mkdir -p "$SANDBOX/bin"
    cat > "$SANDBOX/bin/gh" <<'EOF'
#!/usr/bin/env bash
cat "${GH_STUB_JSON:?}"
EOF
    chmod +x "$SANDBOX/bin/gh"
    export PATH="$SANDBOX/bin:$PATH"

    export GH_STUB_JSON="$SANDBOX/prs.json"
    cat > "$GH_STUB_JSON" <<'JSON'
[
 {"number":1,"title":"Clean feature","author":{"login":"a"},"updatedAt":"2026-05-30T00:00:00Z","mergeable":"MERGEABLE","isDraft":false,"headRefName":"feat","statusCheckRollup":[{"conclusion":"SUCCESS"}]},
 {"number":2,"title":"Conflicts","author":{"login":"b"},"updatedAt":"2026-01-01T00:00:00Z","mergeable":"CONFLICTING","isDraft":false,"headRefName":"old","statusCheckRollup":[]},
 {"number":4,"title":"Draft","author":{"login":"d"},"updatedAt":"2026-05-31T00:00:00Z","mergeable":"MERGEABLE","isDraft":true,"headRefName":"wip","statusCheckRollup":[{"state":"PENDING"}]}
]
JSON
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "enumerates all open PRs" {
    run "$SCRIPT" --platform github
    assert_success
    assert_output --partial "Open PRs on github: 3"
}

@test "clean + passing PR is recommended for merge" {
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==1)["disposition"]=="merge"'
}

@test "conflicting PR is recommended for rebase" {
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==2)["disposition"]=="needs-rebase"'
}

@test "draft PR is kept" {
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==4)["disposition"]=="keep"'
}

@test "empty queue reports clean without error" {
    echo "[]" > "$GH_STUB_JSON"
    run "$SCRIPT" --platform github
    assert_success
    assert_output --partial "Clean queue"
}

@test "superseded PR (shared head branch) is recommended for close" {
    cat > "$GH_STUB_JSON" <<'JSON'
[
 {"number":10,"title":"first","author":{"login":"a"},"updatedAt":"2026-05-30T00:00:00Z","mergeable":"MERGEABLE","isDraft":false,"headRefName":"shared","statusCheckRollup":[{"conclusion":"SUCCESS"}]},
 {"number":11,"title":"dup","author":{"login":"a"},"updatedAt":"2026-05-31T00:00:00Z","mergeable":"MERGEABLE","isDraft":false,"headRefName":"shared","statusCheckRollup":[{"conclusion":"SUCCESS"}]}
]
JSON
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==11)["disposition"]=="close"'
}

@test "unsupported platform errors with exit 2" {
    run "$SCRIPT" --platform bitbucket
    assert_failure
    assert_equal "$status" 2
}

@test "missing platform CLI reports an enumeration error (not a clean queue)" {
    # PATH without gh/glab: default_fetch should fail and surface the auth/CLI hint.
    run env PATH="/usr/bin:/bin" "$SCRIPT" --platform github
    assert_failure
    assert_output --partial "cannot enumerate PRs"
}
