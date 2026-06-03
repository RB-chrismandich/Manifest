#!/usr/bin/env bats
# Tests for configs/claude/scripts/pr_review.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/pr_review.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/pr_review.XXXXXX")
    cat > "$SANDBOX/fetch.sh" <<'EOF'
#!/usr/bin/env bash
cat <<'JSON'
[
 {"number":1,"title":"Clean feature","author":"a","updated":"2026-05-30T00:00:00Z","mergeable":"CLEAN","checks":"PASS","draft":false,"head":"feat","merged":false},
 {"number":2,"title":"Conflicts","author":"b","updated":"2026-01-01T00:00:00Z","mergeable":"CONFLICTING","checks":"NONE","draft":false,"head":"old","merged":false},
 {"number":3,"title":"Merged","author":"c","updated":"2026-05-29T00:00:00Z","mergeable":"UNKNOWN","checks":"NONE","draft":false,"head":"done","merged":true},
 {"number":4,"title":"Draft","author":"d","updated":"2026-05-31T00:00:00Z","mergeable":"CLEAN","checks":"PENDING","draft":true,"head":"wip","merged":false}
]
JSON
EOF
    chmod +x "$SANDBOX/fetch.sh"
    export PR_REVIEW_FETCH="$SANDBOX/fetch.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "enumerates all open PRs" {
    run "$SCRIPT" --platform github
    assert_success
    assert_output --partial "Open PRs on github: 4"
}

@test "clean + passing PR is recommended for merge" {
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==1)["disposition"]=="merge"'
}

@test "merged branch is recommended for close" {
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==3)["disposition"]=="close"'
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
    cat > "$SANDBOX/empty.sh" <<'EOF'
#!/usr/bin/env bash
echo "[]"
EOF
    chmod +x "$SANDBOX/empty.sh"
    export PR_REVIEW_FETCH="$SANDBOX/empty.sh"
    run "$SCRIPT" --platform github
    assert_success
    assert_output --partial "Clean queue"
}

@test "superseded PR (shared head branch) is recommended for close" {
    cat > "$SANDBOX/dup.sh" <<'EOF'
#!/usr/bin/env bash
cat <<'JSON'
[
 {"number":10,"title":"first","author":"a","updated":"2026-05-30T00:00:00Z","mergeable":"CLEAN","checks":"PASS","draft":false,"head":"shared","merged":false},
 {"number":11,"title":"dup","author":"a","updated":"2026-05-31T00:00:00Z","mergeable":"CLEAN","checks":"PASS","draft":false,"head":"shared","merged":false}
]
JSON
EOF
    chmod +x "$SANDBOX/dup.sh"
    export PR_REVIEW_FETCH="$SANDBOX/dup.sh"
    run "$SCRIPT" --platform github --json
    assert_success
    echo "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert next(r for r in d if r["number"]==11)["disposition"]=="close"'
}

@test "unsupported platform errors with exit 2" {
    unset PR_REVIEW_FETCH
    run "$SCRIPT" --platform bitbucket
    assert_failure
    assert_equal "$status" 2
}

@test "missing platform CLI reports an enumeration error (not a clean queue)" {
    unset PR_REVIEW_FETCH
    # PATH without gh/glab: default_fetch should fail and surface the auth/CLI hint.
    run env PATH="/usr/bin:/bin" "$SCRIPT" --platform github
    assert_failure
    assert_output --partial "cannot enumerate PRs"
}
