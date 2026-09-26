#!/usr/bin/env bats
# Tests for orphan-rule pruning in deploy_cursor_configs() / prune_cursor_rules()
# (bootstrap/lib/deploy.sh), spec 2026-07-11-cursor-feature-parity WS-3 (#505).
#
# deploy_cursor_configs() reads $SCRIPT_DIR/configs/cursor as its source and
# writes to $CURSOR_TARGET_DIR, so the hermetic seam is a sandbox that mirrors
# that layout — no dependency on the real repo's rule set.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    # Isolate the APM domain registry — this suite drives a writer that stands
    # down for an APM-owned domain, so without this it reads the developer's
    # live registry instead of a fixture (see apm_test_isolation_guard.bats).
    export MANIFEST_APM_DOMAINS="$BATS_TEST_TMPDIR/no-apm-domains.yml"
    printf 'domains: []\n' > "$MANIFEST_APM_DOMAINS"

    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/deploy_cursor_prune.XXXXXX")

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"

    SRC_RULES="$SANDBOX/repo/configs/cursor/rules"
    mkdir -p "$SRC_RULES"

    export SCRIPT_DIR="$SANDBOX/repo"
    export TARGET_DIR="$SANDBOX/home/.claude"     # unused by cursor deploy; kept for link_shared_assets no-op
    export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
    export ENABLE_CURSOR=true
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

make_rule() {
    local name="$1" body="${2:-body}"
    echo "$body" > "$SRC_RULES/$name.mdc"
}

write_generated_rule() {
    local path="$1" name="$2" body="${3:-generated body}"
    cat > "$path" <<EOF
$body
<!-- Auto-generated from .claude/skills/$name/SKILL.md -->
<!-- Regenerate with: .claude/scripts/generate_cursor_rules.sh -->
EOF
}

make_generated_rule() {
    local name="$1" body="${2:-generated body}"
    write_generated_rule "$SRC_RULES/$name.mdc" "$name" "$body"
}

# ── Baseline deploy ──────────────────────────────────────────────────────────

@test "fresh deploy copies all source rules and writes a manifest" {
    make_rule alpha
    make_rule beta

    run deploy_cursor_configs
    assert_success
    [ -f "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/beta.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/.deployed-rules" ]
    assert_equal "$(cat "$CURSOR_TARGET_DIR/rules/.deployed-rules")" "$(printf 'alpha.mdc\nbeta.mdc')"
}

# ── Recovery when the ownership manifest is absent ─────────────────────────

@test "absent manifest removes an exactly marked generated orphan" {
    make_generated_rule alpha "canonical alpha"
    mkdir -p "$CURSOR_TARGET_DIR/rules"
    write_generated_rule "$CURSOR_TARGET_DIR/rules/retired.mdc" retired "stale retired rule"

    run deploy_cursor_configs
    assert_success
    assert_output --partial "Pruned orphan Cursor rule: retired.mdc"
    [ ! -e "$CURSOR_TARGET_DIR/rules/retired.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]
    assert_equal "$(cat "$CURSOR_TARGET_DIR/rules/.deployed-rules")" "alpha.mdc"
}

@test "absent manifest refreshes an exactly marked generated counterpart" {
    make_generated_rule alpha "canonical alpha"
    mkdir -p "$CURSOR_TARGET_DIR/rules"
    write_generated_rule "$CURSOR_TARGET_DIR/rules/alpha.mdc" alpha "stale alpha"

    run deploy_cursor_configs
    assert_success
    run cmp "$SRC_RULES/alpha.mdc" "$CURSOR_TARGET_DIR/rules/alpha.mdc"
    assert_success
    assert_equal "$(cat "$CURSOR_TARGET_DIR/rules/.deployed-rules")" "alpha.mdc"
}

@test "absent manifest preserves generated-marker lookalikes" {
    make_generated_rule alpha "canonical alpha"
    mkdir -p "$CURSOR_TARGET_DIR/rules"
    cat > "$CURSOR_TARGET_DIR/rules/alpha.mdc" <<'EOF'
user-authored alpha
<!-- Auto-generated from .claude/skills/alpha/SKILL.md -->
<!-- Regenerate with: .claude/scripts/generate_cursor_rules.sh (maybe) -->
EOF
    cat > "$CURSOR_TARGET_DIR/rules/retired.mdc" <<'EOF'
user-authored retired
<!-- Auto-generated from .claude/skills/retired/SKILL.md (maybe) -->
<!-- Regenerate with: .claude/scripts/generate_cursor_rules.sh -->
EOF

    run deploy_cursor_configs
    assert_success
    assert_output --partial "Preserved unrecognized Cursor rule: alpha.mdc"
    assert_equal "$(sed -n '1p' "$CURSOR_TARGET_DIR/rules/alpha.mdc")" "user-authored alpha"
    assert_equal "$(sed -n '1p' "$CURSOR_TARGET_DIR/rules/retired.mdc")" "user-authored retired"
    run cat "$CURSOR_TARGET_DIR/rules/.deployed-rules"
    refute_output --partial "alpha.mdc"
    refute_output --partial "retired.mdc"
}

@test "absent manifest preserves modified markerless orchestration as a conflict" {
    make_generated_rule alpha "canonical alpha"
    make_rule orchestration "canonical orchestration"
    mkdir -p "$CURSOR_TARGET_DIR/rules"
    printf '%s\n' "user-modified orchestration" > "$CURSOR_TARGET_DIR/rules/orchestration.mdc"

    run deploy_cursor_configs
    assert_success
    assert_output --partial "Cursor rule conflict: orchestration.mdc"
    assert_equal "$(cat "$CURSOR_TARGET_DIR/rules/orchestration.mdc")" "user-modified orchestration"
    run cat "$CURSOR_TARGET_DIR/rules/.deployed-rules"
    refute_output --partial "orchestration.mdc"
}

@test "absent manifest records markerless orchestration only after canonical byte match" {
    make_generated_rule alpha "canonical alpha"
    make_rule orchestration "canonical orchestration"
    mkdir -p "$CURSOR_TARGET_DIR/rules"
    cp "$SRC_RULES/orchestration.mdc" "$CURSOR_TARGET_DIR/rules/orchestration.mdc"

    run deploy_cursor_configs
    assert_success
    run cat "$CURSOR_TARGET_DIR/rules/.deployed-rules"
    assert_output --partial "orchestration.mdc"
}

@test "absent-manifest recovery is idempotent on the second run" {
    make_generated_rule alpha "canonical alpha"
    mkdir -p "$CURSOR_TARGET_DIR/rules"
    write_generated_rule "$CURSOR_TARGET_DIR/rules/alpha.mdc" alpha "stale alpha"
    write_generated_rule "$CURSOR_TARGET_DIR/rules/retired.mdc" retired "stale retired rule"

    deploy_cursor_configs
    local first_manifest
    first_manifest="$(cat "$CURSOR_TARGET_DIR/rules/.deployed-rules")"

    run deploy_cursor_configs
    assert_success
    refute_output --partial "Pruned orphan Cursor rule:"
    refute_output --partial "Preserved unrecognized Cursor rule:"
    refute_output --partial "Cursor rule conflict:"
    [ ! -e "$CURSOR_TARGET_DIR/rules/retired.mdc" ]
    run cmp "$SRC_RULES/alpha.mdc" "$CURSOR_TARGET_DIR/rules/alpha.mdc"
    assert_success
    assert_equal "$(cat "$CURSOR_TARGET_DIR/rules/.deployed-rules")" "$first_manifest"
}

# ── Orphan pruning ───────────────────────────────────────────────────────────

@test "rule removed from source is pruned from dest on redeploy" {
    make_rule alpha
    make_rule beta
    deploy_cursor_configs
    [ -f "$CURSOR_TARGET_DIR/rules/beta.mdc" ]

    rm -f "$SRC_RULES/beta.mdc"   # source skill removed/renamed upstream
    run deploy_cursor_configs
    assert_success
    assert_output --partial "Pruned orphan Cursor rule: beta.mdc"
    [ ! -e "$CURSOR_TARGET_DIR/rules/beta.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]   # unrelated rule survives
}

@test "renamed rule: old name pruned, new name deployed" {
    make_rule old-name
    deploy_cursor_configs
    [ -f "$CURSOR_TARGET_DIR/rules/old-name.mdc" ]

    mv "$SRC_RULES/old-name.mdc" "$SRC_RULES/new-name.mdc"
    run deploy_cursor_configs
    assert_success
    [ ! -e "$CURSOR_TARGET_DIR/rules/old-name.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/new-name.mdc" ]
}

@test "prune is idempotent — second deploy with unchanged source deletes nothing" {
    make_rule alpha
    make_rule beta
    deploy_cursor_configs
    deploy_cursor_configs

    run deploy_cursor_configs
    assert_success
    refute_output --partial "Pruned orphan Cursor rule:"
    [ -f "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/beta.mdc" ]
}

# ── Safety: user-authored / protected files are never touched ──────────────

@test "user-authored rule never in the manifest survives redeploy and pruning" {
    make_rule alpha
    make_rule keep   # a second source rule so removing alpha below still
                      # leaves >=1 source rule — exercises a real single-rule
                      # prune rather than the empty-source safety bound.
    deploy_cursor_configs

    # User drops their own custom rule directly into ~/.cursor/rules/ — this
    # file was never shipped by us, so it must never enter the manifest and
    # must never be pruned, even across multiple redeploys.
    echo "mine" > "$CURSOR_TARGET_DIR/rules/my-custom-rule.mdc"

    rm -f "$SRC_RULES/alpha.mdc"   # also exercise a real prune in the same run
    run deploy_cursor_configs
    assert_success
    [ -f "$CURSOR_TARGET_DIR/rules/my-custom-rule.mdc" ]
    assert_equal "$(cat "$CURSOR_TARGET_DIR/rules/my-custom-rule.mdc")" "mine"
    [ ! -e "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/keep.mdc" ]
}

@test "protected singleton rules survive removal from source" {
    make_rule alpha
    make_rule orchestration
    make_rule commands-index
    deploy_cursor_configs

    # Markerless orchestration is recorded only after the fresh copy is known
    # to match canonical bytes. commands-index remains outside the manifest.
    run cat "$CURSOR_TARGET_DIR/rules/.deployed-rules"
    assert_output --partial "orchestration.mdc"
    refute_output --partial "commands-index.mdc"

    # Losing either singleton from source must preserve the deployed copy and
    # remove orchestration from the next ownership record, not prune it.
    rm -f "$SRC_RULES/orchestration.mdc" "$SRC_RULES/commands-index.mdc"
    run deploy_cursor_configs
    assert_success
    refute_output --partial "Pruned orphan Cursor rule: orchestration.mdc"
    refute_output --partial "Pruned orphan Cursor rule: commands-index.mdc"
    [ -f "$CURSOR_TARGET_DIR/rules/orchestration.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/commands-index.mdc" ]
    run cat "$CURSOR_TARGET_DIR/rules/.deployed-rules"
    refute_output --partial "orchestration.mdc"
    refute_output --partial "commands-index.mdc"
}

@test "empty source rules never mass-prunes a previously deployed dest" {
    make_rule alpha
    make_rule beta
    deploy_cursor_configs

    # Source rules dir emptied out entirely (e.g. a botched checkout) — the
    # manifest-tracked prune requires >=1 source rule before it prunes at all,
    # mirroring deploy_home_skills's empty-source safety bound.
    rm -f "$SRC_RULES"/*.mdc
    run deploy_cursor_configs
    assert_success
    [ -f "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]
    [ -f "$CURSOR_TARGET_DIR/rules/beta.mdc" ]
}

@test "ENABLE_CURSOR=false skips deploy entirely — no prune side effects" {
    make_rule alpha
    deploy_cursor_configs
    export ENABLE_CURSOR=false

    rm -f "$SRC_RULES/alpha.mdc"
    run deploy_cursor_configs
    assert_success
    [ -f "$CURSOR_TARGET_DIR/rules/alpha.mdc" ]   # untouched: deploy short-circuited
}
