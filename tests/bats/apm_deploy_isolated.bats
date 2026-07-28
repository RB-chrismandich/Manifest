#!/usr/bin/env bats
# T017/T019 — FR-004..FR-007, FR-023, SC-001..SC-004, SC-008.
#
# Written BEFORE the package existed and demonstrated failing against the
# pre-migration pipeline, because a test authored afterwards cannot demonstrate
# it caught anything.
#
# Every case asserts its PRECONDITION before its postcondition. An idempotence
# diff over an empty tree, or an orphan check whose "before" state was never
# established, passes vacuously while proving nothing — that vacuum is the
# specific failure FR-023 exists to prevent.
#
# SC-008 requires each drift CLASS to have a regression test traceable to the
# specific bug it claims to have killed. The named historical instances, mapped
# to the cases that generalize them:
#
#   mcpServers clobber      → "a deploy does not disturb paths it does not own"
#                             (bootstrap rsync overwrote ~/.claude/settings.local.json,
#                             dropping user-added MCP servers; PR #449)
#   __pycache__ orphan      → "a removed source primitive is removed from the home"
#                             (a skill rename left an untracked __pycache__ that
#                             deployed as a phantom 108th skill)
#   unpruned ~/.cursor/rules → same case; bootstrap never pruned that tree
#   toggle-off skill copy   → "a domain the deploy does not own gets no files"
#                             (browser-test deployed even when browser-use was off)
#   stale COMMANDS.md       → out of scope by design: generate_commands_doc.py stays
#                             on the legacy pipeline (T029), so no APM case covers it
#
# Skipped wholesale until the package exists, so the file is honest about what it
# has and has not proven rather than silently passing zero cases.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PKG_MANIFEST="$REPO_ROOT/apm.yml"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_deploy_iso.XXXXXX")"
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME"
    export APM_LOCKFILE="$HOME/.apm/apm.lock.yaml"

    APM_BIN=""
    command -v apm > /dev/null 2>&1 && APM_BIN="apm"
    [[ -z "$APM_BIN" && -x "$HOME/.local/bin/apm" ]] && APM_BIN="$HOME/.local/bin/apm"

    [[ -f "$PKG_MANIFEST" ]] || skip "no apm.yml yet — T018 has not authored the package"
    [[ -n "$APM_BIN" ]] || skip "apm not installed (./bootstrap.sh --enable-apm)"

    # A staged copy of the package: apm hard-fails on symlinks escaping the
    # package root, and a working checkout has configs/claude/.venv. The
    # published git tree does not (it is untracked), so this mirrors what a
    # real install sees.
    STAGE="$SANDBOX/pkg"
    mkdir -p "$STAGE/.apm"
    cp -R "$REPO_ROOT/.apm/skills" "$STAGE/.apm/skills"
    cp "$PKG_MANIFEST" "$STAGE/apm.yml"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

deploy() { (cd "$STAGE" && HOME="$HOME" "$APM_BIN" install --global "$STAGE" --target claude); }
count_skills() { find "$HOME/.claude/skills" -name SKILL.md 2> /dev/null | wc -l | tr -d ' '; }
tree_hash() {
    find "$HOME/.claude" -type f 2> /dev/null | LC_ALL=C sort |
        xargs shasum -a 256 2> /dev/null | sed "s|$HOME||" | shasum -a 256 | awk '{print $1}'
}

@test "FR-004: the deploy reproduces a non-empty tree from package + lockfile" {
    run deploy
    assert_success

    # Precondition made explicit: a non-empty result, so an install that
    # silently no-ops cannot produce an empty-vs-empty pass.
    n="$(count_skills)"
    [ "$n" -gt 100 ] || {
        echo "expected >100 skills, got $n"
        return 1
    }
    [ -f "$APM_LOCKFILE" ]
}

@test "FR-005: re-deploy with unchanged sources is byte-identical" {
    deploy > /dev/null
    before="$(tree_hash)"
    [ -n "$before" ]

    deploy > /dev/null
    after="$(tree_hash)"
    [ "$before" = "$after" ]
}

@test "FR-006: a renamed source primitive removes the old file and adds the new" {
    deploy > /dev/null
    # PRECONDITION: the old name is actually deployed. Without asserting this,
    # a rename that never took hold looks like successful cleanup.
    [ -d "$HOME/.claude/skills/env-check" ]

    mv "$STAGE/.apm/skills/env-check" "$STAGE/.apm/skills/env-check-renamed"
    deploy > /dev/null

    [ ! -e "$HOME/.claude/skills/env-check" ]
    [ -d "$HOME/.claude/skills/env-check-renamed" ]
}

@test "FR-007: a removed source primitive is removed from the home" {
    # Generalizes the __pycache__ orphan and the unpruned ~/.cursor/rules: a
    # deployer with no ownership record cannot remove what it orphaned.
    deploy > /dev/null
    [ -d "$HOME/.claude/skills/env-check" ]

    rm -rf "$STAGE/.apm/skills/env-check"
    deploy > /dev/null

    [ ! -e "$HOME/.claude/skills/env-check" ]
}

@test "V.4: a hand-edit is DETECTED and reported, not silently overwritten" {
    # T017 originally specified "retained and surfaced". Constitution v3.0.0
    # amended V.4 from preserve-and-report to detect-and-report, because the
    # package manager performs the write and preservation is not expressible.
    # The assertion moved with the principle: detection is the obligation.
    deploy > /dev/null
    target="$HOME/.claude/skills/env-check/SKILL.md"
    [ -f "$target" ]

    echo "USER EDIT" >> "$target"

    run env HOME="$HOME" APM_LOCKFILE="$APM_LOCKFILE" \
        "$REPO_ROOT/configs/claude/scripts/apm_drift_report.sh"
    assert_failure
    assert_output --partial "MODIFIED"
    assert_output --partial "env-check/SKILL.md"
}

@test "V.4: a clean tree reports no drift, so the detection is not vacuous" {
    deploy > /dev/null

    run env HOME="$HOME" APM_LOCKFILE="$APM_LOCKFILE" \
        "$REPO_ROOT/configs/claude/scripts/apm_drift_report.sh"
    assert_success
    assert_output --partial "No drift"
}

@test "a corrupted lockfile fails loudly rather than deploying partially" {
    deploy > /dev/null
    printf 'this: [is: not: valid: yaml\n' > "$APM_LOCKFILE"

    run env HOME="$HOME" APM_LOCKFILE="$APM_LOCKFILE" \
        "$REPO_ROOT/configs/claude/scripts/apm_drift_report.sh"
    assert_failure
    refute_output --partial "No drift"
}

@test "the deploy does not disturb paths it does not own" {
    # Generalizes the mcpServers clobber (PR #449): a deploy overwrote
    # ~/.claude/settings.local.json and dropped user-added MCP servers.
    mkdir -p "$HOME/.claude"
    echo '{"mcpServers":{"mine":{}}}' > "$HOME/.claude/settings.local.json"
    mkdir -p "$HOME/.claude/skills/foreign-tool"
    echo "someone else's" > "$HOME/.claude/skills/foreign-tool/SKILL.md"

    deploy > /dev/null

    run cat "$HOME/.claude/settings.local.json"
    assert_output --partial "mine"
    [ -f "$HOME/.claude/skills/foreign-tool/SKILL.md" ]
}

@test "an unverifiable lockfile exits 2, not 0 — cannot-check must not read as clean" {
    # Regression. The hashless (local-install) lockfile shape reported exit 0
    # with a message saying content drift CANNOT be checked. A caller wiring
    # this as a gate would read that as a pass, making "we never checked" and
    # "we checked and it was fine" the same signal.
    printf "lockfile_version: '1'\ndependencies:\n- repo_url: _local/x\n  deployed_files:\n  - .claude/skills/a\n" \
        > "$SANDBOX/nohash.yml"

    run env HOME="$HOME" APM_LOCKFILE="$SANDBOX/nohash.yml" \
        "$REPO_ROOT/configs/claude/scripts/apm_drift_report.sh"
    [ "$status" -eq 2 ]
    assert_output --partial "CANNOT be checked"
}

@test "the JSON schema is identical across clean, drift, and unverifiable" {
    # Regression: the no-lockfile branch omitted "missing", so a consumer doing
    # d["missing"] KeyError'd on that path only.
    printf "lockfile_version: '1'\ndependencies:\n- repo_url: _local/x\n  deployed_files:\n  - .claude/skills/a\n" \
        > "$SANDBOX/nohash.yml"

    for lock in "$SANDBOX/absent.yml" "$SANDBOX/nohash.yml"; do
        run bash -c "HOME='$HOME' APM_LOCKFILE='$lock' '$REPO_ROOT/configs/claude/scripts/apm_drift_report.sh' --json 2>/dev/null | python3 -c 'import json,sys; print(\",\".join(sorted(json.load(sys.stdin))))'"
        assert_output "checked,drifted,missing,status"
    done
}
