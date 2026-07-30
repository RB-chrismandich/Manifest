#!/usr/bin/env bats
# Tests for configs/claude/scripts/manifest-cli.sh (deployed as ~/.local/bin/manifest)
#
# The wrapper is the single entry point every documented `manifest …` call site
# resolves through, so its failure modes are the CLI's failure modes. Each test
# below is one way a runtime can be present-but-unusable, plus the diagnosis the
# wrapper is required to produce instead of bash's exec noise.

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
WRAPPER="$REPO_ROOT/configs/claude/scripts/manifest-cli.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/manifest_wrapper.XXXXXX")
    export HOME="$SANDBOX/home"
    export MANIFEST_STATE_ROOT="$HOME/.manifest"
    mkdir -p "$HOME/.claude"
    # Minimal PATH by default: the wrapper must never depend on uv, which lives
    # outside a launchd/cron PATH on every machine bootstrap installs it on.
    MINIMAL_PATH="/usr/bin:/bin"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

# A runnable stand-in for the venv console script, echoing argv so passthrough is
# observable and exiting with a code the caller can pin.
_stub_runtime() {
    local exit_code="${1:-0}"
    mkdir -p "$HOME/.claude/.venv/bin"
    cat > "$HOME/.claude/.venv/bin/manifest" << STUB
#!/bin/sh
echo "RAN:\$*"
exit $exit_code
STUB
    chmod +x "$HOME/.claude/.venv/bin/manifest"
}

_run_wrapper() {
    run env HOME="$HOME" MANIFEST_STATE_ROOT="$MANIFEST_STATE_ROOT" \
        PATH="$MINIMAL_PATH" bash "$WRAPPER" "$@"
}

@test "runs the home runtime when uv is absent from PATH" {
    # Regression: gating the exec path on uv made every minimal-PATH context
    # (launchd, cron, hooks) fail against a perfectly healthy runtime.
    _stub_runtime
    _run_wrapper doctor
    assert_success
    assert_output "RAN:doctor"
}

@test "forwards argv byte-for-byte and preserves the exit code" {
    _stub_runtime 42
    _run_wrapper parallel-agent --json "two words" '$literal' --
    assert_failure 42
    assert_output "RAN:parallel-agent --json two words \$literal --"
}

@test "exits 1 with home runtime message when venv manifest is missing" {
    _run_wrapper --help
    assert_failure
    assert_output --partial "home runtime not installed"
}

@test "names the deploying clone from the state stamp when ~/.claude is gone" {
    mkdir -p "$MANIFEST_STATE_ROOT"
    echo "clone_path=$REPO_ROOT" > "$MANIFEST_STATE_ROOT/runtime.env"
    rm -rf "$HOME/.claude"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "home runtime not installed"
    assert_output --partial "re-run $REPO_ROOT/bootstrap.sh"
}

@test "falls back to the deploy stamp for the clone path" {
    mkdir -p "$HOME/.claude/config"
    echo "clone_path=$REPO_ROOT" > "$HOME/.claude/config/deploy_stamp"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "re-run $REPO_ROOT/bootstrap.sh"
}

@test "ignores a stamped clone path that no longer exists" {
    mkdir -p "$MANIFEST_STATE_ROOT"
    echo "clone_path=$SANDBOX/deleted-clone" > "$MANIFEST_STATE_ROOT/runtime.env"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "re-run ./bootstrap.sh"
}

@test "distinguishes an interrupted sync from a missing venv" {
    mkdir -p "$HOME/.claude/.venv/bin"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "home runtime incomplete"
}

@test "reports a lost executable bit precisely" {
    _stub_runtime
    chmod -x "$HOME/.claude/.venv/bin/manifest"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "not executable"
}

@test "reports a stale interpreter path instead of 'bad interpreter'" {
    # What a venv copied from another machine or home directory looks like.
    mkdir -p "$HOME/.claude/.venv/bin"
    printf '#!%s/old-home/.venv/bin/python3\nprint("x")\n' "$SANDBOX" \
        > "$HOME/.claude/.venv/bin/manifest"
    chmod +x "$HOME/.claude/.venv/bin/manifest"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "home runtime is broken"
    refute_output --partial "bad interpreter"
}

@test "reports a truncated entry point instead of running it as a shell script" {
    # A zero-byte console script (full disk) is ENOEXEC, which makes bash
    # reinterpret the file as a shell script rather than fail.
    mkdir -p "$HOME/.claude/.venv/bin"
    : > "$HOME/.claude/.venv/bin/manifest"
    chmod +x "$HOME/.claude/.venv/bin/manifest"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "home runtime is corrupt"
}

@test "accepts an env-style shebang when the venv interpreter is present" {
    mkdir -p "$HOME/.claude/.venv/bin"
    printf '#!/usr/bin/env sh\necho RAN:env\n' > "$HOME/.claude/.venv/bin/manifest"
    chmod +x "$HOME/.claude/.venv/bin/manifest"
    ln -sf /bin/sh "$HOME/.claude/.venv/bin/python3"
    _run_wrapper doctor
    assert_success
    assert_output "RAN:env"
}

@test "rejects an env-style shebang when the venv interpreter is dead" {
    mkdir -p "$HOME/.claude/.venv/bin"
    printf '#!/usr/bin/env python3\nprint("x")\n' > "$HOME/.claude/.venv/bin/manifest"
    chmod +x "$HOME/.claude/.venv/bin/manifest"
    ln -sf "$SANDBOX/gone/python3" "$HOME/.claude/.venv/bin/python3"
    _run_wrapper doctor
    assert_failure
    assert_output --partial "home runtime is broken"
}

@test "MANIFEST_HOME relocates the runtime root" {
    mkdir -p "$SANDBOX/alt/.venv/bin"
    printf '#!/bin/sh\necho RAN:alt\n' > "$SANDBOX/alt/.venv/bin/manifest"
    chmod +x "$SANDBOX/alt/.venv/bin/manifest"
    run env HOME="$HOME" MANIFEST_HOME="$SANDBOX/alt" PATH="$MINIMAL_PATH" \
        bash "$WRAPPER" doctor
    assert_success
    assert_output "RAN:alt"
}

@test "survives an unset HOME instead of aborting on an unbound variable" {
    mkdir -p "$SANDBOX/alt/.venv/bin"
    printf '#!/bin/sh\necho RAN:nohome\n' > "$SANDBOX/alt/.venv/bin/manifest"
    chmod +x "$SANDBOX/alt/.venv/bin/manifest"
    run env -u HOME MANIFEST_HOME="$SANDBOX/alt" PATH="$MINIMAL_PATH" \
        bash "$WRAPPER" doctor
    assert_success
    assert_output "RAN:nohome"
}

@test "unset HOME without MANIFEST_HOME still reports a manifest error" {
    # Whatever it resolves to, the failure must be the wrapper's diagnostic, not
    # bash's `HOME: unbound variable`.
    run env -u HOME PATH="$MINIMAL_PATH" bash "$WRAPPER" doctor
    refute_output --partial "unbound variable"
}

@test "error output carries no escape codes when stderr is not a tty" {
    _run_wrapper doctor
    assert_failure
    refute_output --partial $'\033'
}

@test "the shared PATH-prep idiom never dereferences an unguarded HOME" {
    # The four scripts that shell out to `manifest` prepend ~/.local/bin to PATH
    # above their --help handling. Under `set -u` a bare $HOME there aborts in a
    # clean env (env -i), which is how a repo-convention violation reached the
    # suite once already: PATH=/usr/bin:/bin still carries HOME, so only env -i
    # catches it.
    local script
    for script in skillclaw_promote verification_gate lifecycle spec_review; do
        run grep -c '"\$HOME/\.local/bin:\$PATH"' \
            "$REPO_ROOT/configs/claude/scripts/$script.sh"
        assert_output "0"
    done
}

@test "the wrapper needs neither HOME nor PATH to report or to run" {
    run env -i /bin/bash "$WRAPPER" --version
    refute_output --partial "unbound variable"
}
