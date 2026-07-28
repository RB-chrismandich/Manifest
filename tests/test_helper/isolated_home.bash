# isolated_home.bash — T008/FR-022/FR-035a — isolated-HOME deploy harness.
#
# Every deploy test must run against a throwaway HOME, and the isolation must be
# ASSERTED rather than assumed. The T003 spike sentinel established why: if a
# tool resolves the OS home via a syscall that ignores $HOME, every "isolated"
# result is silently invalid while reporting clean. That check ran once, by
# hand. This makes it runnable on every deploy-test run.
#
# The spike sentinel hashed 94,243 files and took ~90 seconds — correct for a
# one-off gate, unusable per-test. This narrows to the surface a deploy can
# actually write, which is what makes it cheap enough to always run:
#
#   ~/.apm                       created by apm at any invocation (T001 finding 4)
#   ~/.claude/settings.json      where hooks land at user scope
#   ~/.claude/skills             the MVP domain's entry list
#   a canary inside ~/.claude    proves the check can detect a real write
#
# Narrower is not weaker here: it is the difference between hashing files no
# deploy has ever touched and hashing the ones it targets. The canary is what
# keeps it honest — a check that cannot fail proves nothing, so
# isolated_home_assert_clean refuses to certify unless the control fired.

# isolated_home_begin <sandbox_dir> — export an isolated HOME and snapshot the
# real one's deploy surface. Call from setup().
isolated_home_begin() {
    local sandbox="$1"
    ISOLATED_REAL_HOME="$HOME"
    ISOLATED_SNAPSHOT="$sandbox/.real-home-snapshot"
    ISOLATED_CANARY="$ISOLATED_REAL_HOME/.claude/.isolation-canary"

    mkdir -p "$ISOLATED_REAL_HOME/.claude" 2> /dev/null || true
    printf 'isolation canary %s\n' "$$" > "$ISOLATED_CANARY" 2> /dev/null || true

    _isolated_home_surface > "$ISOLATED_SNAPSHOT"

    export HOME="$sandbox/home"
    mkdir -p "$HOME"
}

# The deploy surface, as a stable text fingerprint. Cheap by construction: one
# find over two directories plus two file hashes.
_isolated_home_surface() {
    local h="${ISOLATED_REAL_HOME}"
    echo "apm_dir_exists=$([[ -e "$h/.apm" ]] && echo yes || echo no)"
    echo "settings=$(shasum -a 256 "$h/.claude/settings.json" 2> /dev/null | awk '{print $1}')"
    echo "canary=$(shasum -a 256 "$h/.claude/.isolation-canary" 2> /dev/null | awk '{print $1}')"
    echo "skills=$(find "$h/.claude/skills" -maxdepth 1 -mindepth 1 2> /dev/null | LC_ALL=C sort | shasum -a 256 | awk '{print $1}')"
}

# isolated_home_assert_clean — the real home is untouched, and the check that
# says so is one that could have failed. Call from teardown() or at the end of
# a deploy test.
isolated_home_assert_clean() {
    local real_home="$ISOLATED_REAL_HOME"

    # Control first: mutate the canary and require the fingerprint to CHANGE.
    #
    # Compare before-vs-after, not after-vs-snapshot. Comparing against the
    # snapshot looks equivalent and is not: a fingerprint stuck on a constant
    # also differs from the snapshot, so it would sail through the control and
    # then fail the real assertion with a misleading "the real HOME was
    # modified". Only a before/after pair proves the check responds to a write.
    local control_before control_after
    control_before="$(_isolated_home_surface)"
    printf 'mutated\n' >> "$ISOLATED_CANARY" 2> /dev/null || true
    control_after="$(_isolated_home_surface)"
    if [[ "$control_before" == "$control_after" ]]; then
        HOME="$real_home"
        rm -f "$ISOLATED_CANARY"
        echo "isolation harness: CONTROL FAILED — the check cannot detect a real write" >&2
        return 1
    fi
    rm -f "$ISOLATED_CANARY"

    # Now the real assertion, with the canary removed on both sides.
    local now snapshot
    now="$(_isolated_home_surface)"
    snapshot="$(grep -v '^canary=' "$ISOLATED_SNAPSHOT")"
    now="$(printf '%s\n' "$now" | grep -v '^canary=')"

    HOME="$real_home"
    if [[ "$now" != "$snapshot" ]]; then
        echo "isolation harness: the real HOME was modified by an isolated run:" >&2
        diff <(printf '%s\n' "$snapshot") <(printf '%s\n' "$now") >&2 || true
        return 1
    fi
    return 0
}
