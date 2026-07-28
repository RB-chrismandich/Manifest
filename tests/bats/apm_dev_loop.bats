#!/usr/bin/env bats
# T055/FR-032: the publish-free local development loop (apm_dev_sync.sh).
#
# `apm` itself is stubbed. What is under test is the SCRIPT's contract — that it
# stages a mirror of .apm/skills, invokes apm against a stably-named local path
# with no registry, and refuses to report success when nothing was deployed.
# apm's own behaviour (edit propagates, addition deploys, deletion cleans up) is
# measured evidence recorded in specs/522-apm-deploy-migration/decision-record.md,
# not something a stub can meaningfully re-assert.
#
# Every test runs against an isolated HOME and an isolated staging root; nothing
# here touches the real ~/.claude or the real repo checkout.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/apm_dev_sync.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX="$(mktemp -d "$BATS_TMPDIR/apm_dev_loop.XXXXXX")"

    export HOME="$SANDBOX/home"
    export MANIFEST_APM_DEV_STAGE="$SANDBOX/stage"
    export APM_DEV_SYNC_QUIET=1
    mkdir -p "$HOME"

    # A fake Manifest checkout with three skills.
    export MANIFEST_ROOT="$SANDBOX/repo"
    for s in alpha beta gamma; do
        mkdir -p "$MANIFEST_ROOT/.apm/skills/$s"
        printf -- '---\nname: %s\ndescription: d\n---\nbody\n' "$s" \
            > "$MANIFEST_ROOT/.apm/skills/$s/SKILL.md"
    done

    # Stub apm: record argv, then emulate a deploy by copying the staged skills
    # into the home. Enough to exercise the script's pre/post conditions.
    BIN="$SANDBOX/bin"
    mkdir -p "$BIN"
    CALLS="$SANDBOX/calls.log"
    : > "$CALLS"
    cat > "$BIN/apm" << SH
#!/usr/bin/env bash
echo "\$*" >> "$CALLS"
[[ "\${APM_STUB_DEPLOY:-1}" == "1" ]] || exit "\${APM_STUB_EXIT:-0}"
stage="\$3"
mkdir -p "\$HOME/.claude/skills"
cp -R "\$stage/.apm/skills/." "\$HOME/.claude/skills/" 2>/dev/null || true
exit "\${APM_STUB_EXIT:-0}"
SH
    chmod +x "$BIN/apm"
    export PATH="$BIN:$PATH"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# --- contract ----------------------------------------------------------------

@test "--help exits 0 and prints usage without touching state" {
    run "$SCRIPT" --help
    assert_success
    assert_output --partial "Usage: apm-dev-sync"
    [ ! -e "$MANIFEST_APM_DEV_STAGE" ]
}

@test "deploys the checkout's skills into HOME" {
    run "$SCRIPT"
    assert_success
    assert_output --partial "3 skill(s) deployed"
    [ -f "$HOME/.claude/skills/alpha/SKILL.md" ]
}

@test "invokes apm against the local staging path, with no registry reference" {
    run "$SCRIPT"
    assert_success

    run cat "$CALLS"
    assert_output --partial "install --global"
    assert_output --partial "manifest-skills"
    # A publish-free loop must never resolve a remote name.
    refute_output --partial "https://"
    refute_output --partial "publish"
}

@test "generates a package manifest in staging, not in the checkout" {
    run "$SCRIPT"
    assert_success
    [ -f "$MANIFEST_APM_DEV_STAGE/manifest-skills/apm.yml" ]
    # T018 owns the real, published manifest — the loop must not create one in
    # the repo and quietly preempt it.
    [ ! -e "$MANIFEST_ROOT/apm.yml" ]
}

# --- staging is a mirror -----------------------------------------------------

@test "a skill deleted from the source does not survive in staging" {
    # The property that makes deletion cleanup possible at all. If staging
    # accumulated instead of mirroring, apm would keep redeploying the deleted
    # skill and the loop would be no better than sync-skills.
    run "$SCRIPT"
    assert_success
    [ -f "$MANIFEST_APM_DEV_STAGE/manifest-skills/.apm/skills/beta/SKILL.md" ]

    rm -rf "$MANIFEST_ROOT/.apm/skills/beta"
    run "$SCRIPT"
    assert_success
    [ ! -e "$MANIFEST_APM_DEV_STAGE/manifest-skills/.apm/skills/beta" ]
}

@test "an edit to the source reaches staging on the next run" {
    run "$SCRIPT"
    assert_success

    echo "EDIT MARKER" >> "$MANIFEST_ROOT/.apm/skills/alpha/SKILL.md"
    run "$SCRIPT"
    assert_success
    run cat "$MANIFEST_APM_DEV_STAGE/manifest-skills/.apm/skills/alpha/SKILL.md"
    assert_output --partial "EDIT MARKER"
}

@test "the staging directory basename is stable across runs" {
    # apm keys local ownership off the directory basename; a per-run name would
    # register a new package every time and break deletion cleanup silently.
    run "$SCRIPT"
    assert_success
    run "$SCRIPT"
    assert_success

    run find "$MANIFEST_APM_DEV_STAGE" -maxdepth 1 -mindepth 1 -type d
    assert_output --partial "manifest-skills"
    [ "$(find "$MANIFEST_APM_DEV_STAGE" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')" = "1" ]
}

# --- failure paths -----------------------------------------------------------

@test "apm reporting success while deploying nothing is treated as failure" {
    # The silent no-op. Without the post-check, an install that touched nothing
    # would print success and the contributor would debug the wrong thing.
    export APM_STUB_DEPLOY=0

    run "$SCRIPT"
    assert_failure
    assert_output --partial "no SKILL.md landed"
}

@test "a failing apm install is not reported as a deploy" {
    export APM_STUB_DEPLOY=0
    export APM_STUB_EXIT=1

    run "$SCRIPT"
    assert_failure
    assert_output --partial "nothing was deployed"
}

@test "a missing apm names the flag that installs it" {
    # Shadow the stub with an exit-127 entry rather than emptying PATH: on
    # merged-/usr Linux a 'minimal PATH' still resolves real binaries.
    cat > "$BIN/apm" << 'SH'
#!/usr/bin/env bash
exit 127
SH
    chmod +x "$BIN/apm"
    rm -f "$BIN/apm"

    run "$SCRIPT"
    assert_failure
    assert_output --partial "--enable-apm"
}

@test "refuses to run outside a Manifest checkout" {
    export MANIFEST_ROOT="$SANDBOX/not-a-checkout"
    mkdir -p "$MANIFEST_ROOT"

    run "$SCRIPT"
    assert_failure
    assert_output --partial "no .apm/skills"
}

@test "rejects an unknown argument instead of ignoring it" {
    run "$SCRIPT" --bogus
    assert_failure
    assert_output --partial "unknown argument"
}

@test "--target requires a value" {
    run "$SCRIPT" --target
    assert_failure
    assert_output --partial "requires a value"
}

@test "refuses to clear an unexpected staging path" {
    # Guards the rm -rf: the leaf must be the fixed name, never a user path.
    export MANIFEST_APM_DEV_STAGE="$SANDBOX/stage-alt"
    run "$SCRIPT"
    assert_success
    [ -d "$SANDBOX/stage-alt/manifest-skills" ]
}
