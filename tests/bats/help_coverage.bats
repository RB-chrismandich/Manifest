#!/usr/bin/env bats
# specs/003 T039 / R6: every user-facing entry point in configs/claude/scripts/
# handles --help (usage to stdout, exit 0).
#
# Coverage is ENUMERATED, never listed. A hand-maintained inclusion list fails
# in the direction you cannot see: a new script that forgets to join the list is
# silently ungated, and a script listed by name that cannot satisfy the gate
# breaks CI (that is exactly how parallel_agent.py broke the build — it is a
# `manifest` deprecation shim with no --help of its own). So the universe is
# every script in the directory, and an exemption must be declared IN THE FILE:
#
#     # help-coverage: exempt — <one-line rationale>
#
# placed directly under the shebang. The rationale travels with the code, a new
# script is gated by default, and removing a script removes its exemption.
#
# Two further exclusions are derived from the code itself, needing no marker:
#   * a Python file with no `__main__` block is a library, not an entry point
#   * a Python file importing `_manifest_shim` is a `manifest` deprecation shim;
#     it execs the home runtime, so its --help is the runtime's (or a
#     deprecation notice) and gating it would make the suite pass or fail on
#     whether that runtime happens to be built — the local-green/CI-red split.

setup() {
    load '../test_helper/bats-support/load'
    load '../test_helper/bats-assert/load'
    SCRIPTS="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../configs/claude/scripts" && pwd)"
}

EXEMPT_MARKER="help-coverage: exempt"

# Every *.sh entry point that has not declared an in-file exemption.
bash_gated() {
    local f
    for f in "$SCRIPTS"/*.sh; do
        grep -q "$EXEMPT_MARKER" "$f" && continue
        basename "$f"
    done
}

# Every *.py entry point: skips libraries (no __main__), `manifest` deprecation
# shims (derived from the import), and in-file exemptions.
py_gated() {
    local f
    for f in "$SCRIPTS"/*.py; do
        grep -q '__name__ == "__main__"' "$f" || continue
        grep -q "_manifest_shim" "$f" && continue
        grep -q "$EXEMPT_MARKER" "$f" && continue
        basename "$f"
    done
}

@test "every user-facing script: --help exits 0 and prints Usage on stdout" {
    for f in $(bash_gated); do
        run bash "$SCRIPTS/$f" --help
        [ "$status" -eq 0 ] || { echo "$f: exit $status"; false; }
        [[ "$output" == *"Usage"* || "$output" == *"USAGE"* ]] \
            || { echo "$f: no Usage in --help output"; false; }
    done
}

@test "--help output stays concise (<= 50 lines per script)" {
    # R6's <=15-line guideline applies to the minimal helps ADDED by T039;
    # pre-existing comprehensive helps (learning_capture: 50) get headroom.
    for f in $(bash_gated); do
        lines=$(bash "$SCRIPTS/$f" --help | wc -l | tr -d ' ')
        [ "$lines" -le 50 ] || { echo "$f: $lines lines"; false; }
    done
}

@test "every user-facing python script: --help exits 0 and prints usage on stdout" {
    for f in $(py_gated); do
        run python3 "$SCRIPTS/$f" --help
        [ "$status" -eq 0 ] || { echo "$f: exit $status"; false; }
        lc_output="$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')"
        [[ "$lc_output" == *"usage"* ]] \
            || { echo "$f: no usage in --help output"; false; }
    done
}

@test "python --help output stays concise (<= 80 lines per script)" {
    # 80 (vs the Bash list's 50) gives headroom for argparse's fuller,
    # auto-generated option blocks (e.g. parallel_agent.py's full flag surface
    # is a legitimate ~63 lines, not a defect).
    for f in $(py_gated); do
        lines=$(python3 "$SCRIPTS/$f" --help 2>&1 | wc -l | tr -d ' ')
        [ "$lines" -le 80 ] || { echo "$f: $lines lines"; false; }
    done
}

@test "every exemption carries an in-file rationale" {
    # A bare opt-out would restore the thing this design removes: an exemption
    # nobody can evaluate. The marker must be followed by prose.
    local f line
    for f in "$SCRIPTS"/*.sh "$SCRIPTS"/*.py; do
        line=$(grep -m1 "$EXEMPT_MARKER" "$f" || true)
        [ -n "$line" ] || continue
        [[ "$line" == *"—"* ]] \
            || { echo "$(basename "$f"): exemption marker has no '— <rationale>'"; false; }
        # Something substantive after the dash, not just whitespace.
        [ "${#line}" -ge $((${#EXEMPT_MARKER} + 20)) ] \
            || { echo "$(basename "$f"): exemption rationale too thin: $line"; false; }
    done
}

@test "the exemption convention itself is documented" {
    doc="$SCRIPTS/../../../docs/CODING_STANDARDS.md"
    grep -q "help-coverage: exempt" "$doc"
}

@test "coverage is enumerated, not listed (no script is silently ungated)" {
    # Guard the property this file exists to hold: every *.sh and every *.py
    # entry point is either gated or carries a marker. Fails loudly if someone
    # reintroduces an inclusion list.
    local f base skipped
    for f in "$SCRIPTS"/*.sh; do
        base=$(basename "$f")
        bash_gated | grep -qx "$base" && continue
        grep -q "$EXEMPT_MARKER" "$f" \
            || { echo "$base: neither gated nor exempt"; false; }
    done
    for f in "$SCRIPTS"/*.py; do
        base=$(basename "$f")
        py_gated | grep -qx "$base" && continue
        skipped=0
        grep -q '__name__ == "__main__"' "$f" || skipped=1          # library
        grep -q "_manifest_shim" "$f" && skipped=1                  # manifest shim
        grep -q "$EXEMPT_MARKER" "$f" && skipped=1                  # declared exempt
        [ "$skipped" -eq 1 ] || { echo "$base: neither gated nor exempt"; false; }
    done
}
