#!/usr/bin/env bats
# The bundle check must not hand out a remedy that cannot work.
#
# verify_installation reports every bundle named in skill_policies.yml but absent
# from installed_plugins.json as:
#
#     Bundle NOT installed: <b> — run: claude plugin install <b>@manifest
#
# That advice is only correct when the registered marketplace actually carries
# <b>. Measured incident, 2026-08-17: the "manifest" marketplace was a
# directory-sourced git worktree pinned at a commit predating
# manifest-i-have-adhd, so it offered 11 of the repo's 12 bundles. The verifier
# reported the 12th as NOT installed and printed the install command, which
# fails — the bundle is not in the marketplace to install. The operator followed
# the instruction, watched it fail, and had to diagnose marketplace drift from
# scratch. A remedy that cannot succeed is worse than no remedy: it spends the
# reader's time asserting the wrong cause.
#
# So the two states get two messages. Whether the bundle is offered is decided by
# marketplace_offers_bundle, tested here directly, three-valued so an unreadable
# or unparseable registry degrades to today's behaviour rather than to a new
# wrong claim.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/bundle_drift.XXXXXX")"
    export TARGET_DIR="$SANDBOX/claude"
    export HOME="$SANDBOX/home"
    mkdir -p "$TARGET_DIR/plugins" "$TARGET_DIR/config" "$HOME"

    source "$REPO_ROOT/bootstrap/lib/common.sh"
    source "$REPO_ROOT/bootstrap/lib/deploy.sh"
}

teardown() {
    [[ -n "${SANDBOX:-}" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    return 0
}

# Write a registered "manifest" marketplace whose checkout carries $* as plugins.
seed_marketplace() {
    local checkout="$SANDBOX/marketplace"
    mkdir -p "$checkout/.claude-plugin"
    local names="" name
    for name in "$@"; do
        names="$names{\"name\": \"$name\", \"source\": \"./plugins/$name\"},"
    done
    printf '{"name": "manifest", "plugins": [%s]}\n' "${names%,}" \
        > "$checkout/.claude-plugin/marketplace.json"
    printf '{"marketplaces": {"manifest": {"installLocation": "%s"}}}\n' "$checkout" \
        > "$TARGET_DIR/plugins/known_marketplaces.json"
}

@test "marketplace_offers_bundle: 0 when the marketplace carries the bundle" {
    seed_marketplace manifest-docs manifest-i-have-adhd
    run marketplace_offers_bundle manifest-i-have-adhd
    assert_equal "$status" 0
}

@test "marketplace_offers_bundle: 1 when registered but the bundle is absent" {
    seed_marketplace manifest-docs manifest-forge
    run marketplace_offers_bundle manifest-i-have-adhd
    assert_equal "$status" 1
}

@test "marketplace_offers_bundle: substring names do not count as offered" {
    # "manifest-doc" must not be satisfied by "manifest-docs".
    seed_marketplace manifest-docs
    run marketplace_offers_bundle manifest-doc
    assert_equal "$status" 1
}

@test "marketplace_offers_bundle: 2 (unknown) when no marketplace is registered" {
    run marketplace_offers_bundle manifest-docs
    assert_equal "$status" 2
}

@test "marketplace_offers_bundle: 2 (unknown) when the registry is unparseable" {
    printf 'not json at all\n' > "$TARGET_DIR/plugins/known_marketplaces.json"
    run marketplace_offers_bundle manifest-docs
    assert_equal "$status" 2
}

@test "marketplace_offers_bundle: 2 (unknown) when the checkout manifest is missing" {
    printf '{"marketplaces": {"manifest": {"installLocation": "%s/gone"}}}\n' "$SANDBOX" \
        > "$TARGET_DIR/plugins/known_marketplaces.json"
    run marketplace_offers_bundle manifest-docs
    assert_equal "$status" 2
}

# ---- wiring: the loop must pick its remedy from that answer ----------------

# Drive the real branch with one missing bundle and capture what it advises.
run_bundle_check() {
    printf 'bundles:\n  manifest-i-have-adhd:  # 1 skill\n' \
        > "$TARGET_DIR/config/skill_policies.yml"
    printf '{"plugins": {"manifest-docs@manifest": {}}}\n' \
        > "$TARGET_DIR/plugins/installed_plugins.json"
    verify_manifest_bundles
}

@test "absent from marketplace: advises the marketplace update, not the install" {
    seed_marketplace manifest-docs
    run run_bundle_check
    assert_output --partial 'marketplace update manifest'
    refute_output --partial 'plugin install manifest-i-have-adhd@manifest'
}

@test "offered by marketplace: still advises the install" {
    seed_marketplace manifest-docs manifest-i-have-adhd
    run run_bundle_check
    assert_output --partial 'plugin install manifest-i-have-adhd@manifest'
    refute_output --partial 'marketplace update manifest'
}

@test "unknown marketplace state: falls back to the install advice" {
    run run_bundle_check
    assert_output --partial 'plugin install manifest-i-have-adhd@manifest'
}

@test "either way the bundle shortfall is still an error, not a warning" {
    seed_marketplace manifest-docs
    run run_bundle_check
    assert_equal "$status" 1
}

@test "real skill_policies.yml discovers manifest-security once despite implicit_invocation_triggers" {
    cp "$REPO_ROOT/configs/claude/config/skill_policies.yml" "$TARGET_DIR/config/skill_policies.yml"
    python3 - "$TARGET_DIR/config/skill_policies.yml" "$TARGET_DIR/plugins/installed_plugins.json" << 'PY'
import json, pathlib, re, sys
text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
in_bundles = False
bundles = []
for line in text.splitlines():
    if line.startswith("bundles:"):
        in_bundles = True
        continue
    if in_bundles and re.match(r"^  [a-z][a-z0-9-]*:\s*(?:#.*)?$", line):
        bundles.append(line.split(":", 1)[0].strip())
plugins = {f"{b}@manifest": {} for b in bundles if b != "manifest-security"}
pathlib.Path(sys.argv[2]).write_text(json.dumps({"plugins": plugins}), encoding="utf-8")
PY

    run verify_manifest_bundles
    assert_equal "$status" 1
    local sec_count
    sec_count="$(printf '%s\n' "$output" | grep -c 'Bundle NOT installed: manifest-security' || true)"
    assert_equal "$sec_count" "1"
}
