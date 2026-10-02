#!/usr/bin/env bats
# T5.4 (spec 674) — drift detection for installed plugin bundles.
#
# Constitution Principle V.3 makes drift detection for owned paths a LIVE
# obligation and named apm_drift_report.sh as its implementation. Phase 5 retires
# that script, so the obligation needs a new subject or the control disappears
# with the tool -- a silent weakening, not a migration.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/plugin_drift_report.sh"

setup() {
    SANDBOX="$(mktemp -d "${BATS_TMPDIR:-/tmp}/pdrift.XXXXXX")"
    export CLAUDE_PLUGIN_CACHE="$SANDBOX/cache"
    SRC="$SANDBOX/repo/plugins/manifest-demo"
    INST="$CLAUDE_PLUGIN_CACHE/manifest-demo/0.1.0"
    mkdir -p "$SRC/skills/alpha" "$INST/skills/alpha"
    echo "body" > "$SRC/skills/alpha/SKILL.md"
    echo "body" > "$INST/skills/alpha/SKILL.md"
}

teardown() { [[ -n "${SANDBOX:-}" ]] && rm -rf "$SANDBOX"; return 0; }

run_drift() { run "$SCRIPT" --repo "$SANDBOX/repo"; }

@test "--help exits 0 and is at most 15 lines" {
    run "$SCRIPT" --help
    assert_success
    [ "${#lines[@]}" -le 15 ]
}

@test "an untouched bundle reports no drift" {
    run_drift
    assert_success
    assert_output --partial "No drift"
}

@test "a hand-edit inside the installed cache is caught" {
    # The whole point: plugins record only gitCommitSha + version, so this edit
    # is invisible to `claude plugin`, and reconcile.yml ignore-lists `plugins`.
    echo "tampered" > "$INST/skills/alpha/SKILL.md"
    run_drift
    assert_failure
    assert_output --partial "DRIFT"
    assert_output --partial "alpha"
}

@test "a file added inside the cache is caught" {
    echo "x" > "$INST/skills/alpha/EXTRA.md"
    run_drift
    assert_failure
}

@test "an ORPHANED version directory is skipped, not reported forever" {
    # `claude plugin update` installs a new version dir and marks the old one
    # .orphaned_at; both stay on disk. Comparing every version dir reports the
    # superseded copy as drift on every run, which is how a real check becomes
    # noise nobody reads.
    local old="$CLAUDE_PLUGIN_CACHE/manifest-demo/0.0.9"
    mkdir -p "$old/skills/alpha"
    echo "ancient" > "$old/skills/alpha/SKILL.md"
    : > "$old/.orphaned_at"
    run_drift
    assert_success
    assert_output --partial "No drift"
}

@test "a bundle with no source tree is UNCHECKED, never clean" {
    # "I could not look" must not render as "nothing is wrong".
    mkdir -p "$CLAUDE_PLUGIN_CACHE/from-github/1.0.0"
    run_drift
    assert_output --partial "UNCHECKED"
    assert_output --partial "from-github"
}

@test "nothing checkable at all is indeterminate, not success" {
    rm -rf "$SANDBOX/repo/plugins"
    run_drift
    [ "$status" -eq 2 ]
    assert_output --partial "Indeterminate"
}

@test "no installed bundles is indeterminate, not success" {
    rm -rf "$CLAUDE_PLUGIN_CACHE"
    run_drift
    [ "$status" -eq 2 ]
}

@test "build litter is not reported as drift" {
    mkdir -p "$INST/skills/alpha/__pycache__"
    echo "x" > "$INST/skills/alpha/__pycache__/a.pyc"
    run_drift
    assert_success
}
