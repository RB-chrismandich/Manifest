#!/usr/bin/env bats
# T008/FR-022/FR-035a/SC-007 — the isolation assertion, run on every deploy-test
# run rather than once by hand.
#
# The T003 spike sentinel answered "does apm honour $HOME?" once, in a scratch
# dir, at 94,243 files and ~90 seconds. That is the right shape for a one-off
# gate and the wrong shape for a per-run check, so this narrows to the surface a
# deploy can actually write and keeps the property that matters: the check is
# proven able to fail before it is believed.
#
# The failure this exists to prevent is specific and has happened: an "isolated"
# run that silently writes the real home while reporting clean. T001 finding 4
# recorded that `apm --help` ALONE creates ~/.apm/config.json, so the tool is
# not side-effect-free at any invocation.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'
load '../test_helper/isolated_home'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_isolation.XXXXXX")"
    isolated_home_begin "$SANDBOX"

    # shellcheck disable=SC1090
    source "$REPO_ROOT/bootstrap/lib/common.sh"
    print_success() { :; }
    print_warning() { :; }
    print_error() { :; }
    print_info() { :; }
    print_step() { :; }

    SRC="$SANDBOX/src"
    for s in alpha beta; do
        mkdir -p "$SRC/$s"
        printf -- '---\nname: %s\ndescription: d\n---\nbody\n' "$s" > "$SRC/$s/SKILL.md"
    done
}

teardown() {
    [[ -n "$ISOLATED_REAL_HOME" ]] && HOME="$ISOLATED_REAL_HOME"
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "HOME is redirected away from the real home" {
    [ "$HOME" != "$ISOLATED_REAL_HOME" ]
    [[ "$HOME" == "$SANDBOX/"* ]] || return 1
}

@test "a real deploy into the isolated HOME leaves the real home untouched" {
    deploy_home_skills "$SRC" "$HOME/.claude/skills"
    [ -f "$HOME/.claude/skills/alpha/SKILL.md" ]

    run isolated_home_assert_clean
    assert_success
}

@test "the harness refuses to certify when its own control cannot fail" {
    # Simulate a fingerprint that reports the same value no matter what. A check
    # that cannot fail must be treated as a failure, not as a pass — this is the
    # defect the spike rig hit twice before the control was added.
    _isolated_home_surface() { echo "constant"; }

    run isolated_home_assert_clean
    assert_failure
    assert_output --partial "CONTROL FAILED"
}

@test "a write to the real home is detected, not reported clean" {
    # The whole point. Write to the real ~/.claude the way a HOME-ignoring tool
    # would, and require the assertion to fail.
    mkdir -p "$ISOLATED_REAL_HOME/.claude/skills/leaked-by-test"

    run isolated_home_assert_clean
    assert_failure
    assert_output --partial "real HOME was modified"

    rmdir "$ISOLATED_REAL_HOME/.claude/skills/leaked-by-test" 2> /dev/null || true
}

@test "creation of ~/.apm in the real home is detected" {
    # T001 finding 4: apm creates ~/.apm/config.json at ANY invocation, so its
    # appearance in the real home is the single highest-signal leak indicator.
    if [[ -e "$ISOLATED_REAL_HOME/.apm" ]]; then
        skip "real ~/.apm already exists; this machine cannot distinguish creation"
    fi
    mkdir -p "$ISOLATED_REAL_HOME/.apm"

    run isolated_home_assert_clean
    assert_failure
    assert_output --partial "apm_dir_exists"

    rmdir "$ISOLATED_REAL_HOME/.apm" 2> /dev/null || true
}

@test "the assertion restores HOME so later tests are not left redirected" {
    run isolated_home_assert_clean
    assert_success
    isolated_home_assert_clean
    [ "$HOME" = "$ISOLATED_REAL_HOME" ]
}

@test "the check is fast enough to run on every deploy test" {
    # A per-run assertion nobody can afford to run is a per-run assertion that
    # gets deleted. The spike's 94k-file hash took ~90s; this must stay in
    # single-digit seconds or the narrowing was pointless.
    local start end
    start=$(date +%s)
    _isolated_home_surface > /dev/null
    end=$(date +%s)
    [ "$((end - start))" -lt 5 ]
}
