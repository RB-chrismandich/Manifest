#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/spec-planning-plugin.XXXXXX")
    cp -R "$REPO_ROOT/plugins/manifest-spec-planning" "$SANDBOX/bundle"
    export HOME="$SANDBOX/home"
    export XDG_DATA_HOME="$SANDBOX/data"
    export XDG_CONFIG_HOME="$SANDBOX/config"
    mkdir -p "$HOME" "$XDG_DATA_HOME" "$XDG_CONFIG_HOME"
    SCRIPT="$SANDBOX/bundle/runtime/spec_review.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "bundle-local spec review prints help with an empty home" {
    run bash "$SCRIPT" --help
    assert_success
    assert_output --partial "spec-review"
    refute_output --partial ".claude"
}

@test "bundle-local spec review discovers and reviews isolated artifacts" {
    mkdir -p "$SANDBOX/project/specs/001"
    printf '# Spec\n' > "$SANDBOX/project/specs/001/spec.md"
    printf '# Plan\n' > "$SANDBOX/project/specs/001/plan.md"
    cat > "$SANDBOX/reviewer" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
printf 'NO_ISSUES\n'
EOF
    chmod +x "$SANDBOX/reviewer"

    run env SPEC_REVIEW_PANEL_CMD=/bin/false SPEC_REVIEW_CLI="$SANDBOX/reviewer" \
        bash "$SCRIPT" "$SANDBOX/project"

    assert_success
    assert_output --partial "No inconsistencies found across 2 artifacts"
}

@test "bundle-local spec review fails when reviewer output is unverifiable" {
    mkdir -p "$SANDBOX/project/specs/001"
    printf '# Spec\n' > "$SANDBOX/project/specs/001/spec.md"
    printf '# Plan\n' > "$SANDBOX/project/specs/001/plan.md"
    cat > "$SANDBOX/reviewer" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
printf 'looks fine\n'
EOF
    chmod +x "$SANDBOX/reviewer"

    run env SPEC_REVIEW_PANEL_CMD=/bin/false SPEC_REVIEW_CLI="$SANDBOX/reviewer" \
        bash "$SCRIPT" "$SANDBOX/project"

    assert_failure
    assert_output --partial "unverifiable reviewer output"
}
