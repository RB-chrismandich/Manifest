# pr_merge_loop_seams.bash — shared offline seam harness for the
# pr_merge_loop*.bats modules. pr_merge_loop.bats crossed the 600-line
# constitution ceiling and split along the lib/ module boundaries; this file
# keeps the seam scripts and helpers in exactly one place. Each module wires:
#
#     source "$BATS_TEST_DIRNAME/../test_helper/pr_merge_loop_seams.bash"
#     setup()    { pr_merge_loop_setup; }
#     teardown() { pr_merge_loop_teardown; }
#
# Sourced by bats modules; not executable on its own.
# help-coverage: exempt — test helper library, no user-facing entry point.

# shellcheck disable=SC2034 # consumed by Bats modules that source this helper.
SCRIPT="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/pr_merge_loop.sh"
# shellcheck disable=SC2034 # consumed by Bats modules that source this helper.
DECIDE="$BATS_TEST_DIRNAME/../../plugins/manifest-forge/runtime/bin/merge_decision.sh"

pr_merge_loop_setup() {
    TMP=$(mktemp -d "${BATS_TMPDIR:-/tmp}/prloop.XXXXXX")
    export TMP PR_MERGE_LOOP_STATE_DIR="$TMP/state"
    # Keep forge XDG state (audit_log.jsonl etc.) inside the sandbox too.
    export XDG_STATE_HOME="$TMP/xdg-state"
    export SEAM_CALL_LOG="$TMP/gh-calls" SEAM_GATE_LOG="$TMP/gate-calls"
    export SEAM_LABEL_LOG="$TMP/label-calls" SEAM_HEAD_DIR="$TMP/heads"
    mkdir -p "$SEAM_HEAD_DIR"
    : > "$SEAM_CALL_LOG"
    : > "$SEAM_GATE_LOG"
    : > "$SEAM_LABEL_LOG"

    # cmd_signals calls cmd_post_merge_check, which first resolves main HEAD via
    # `git ls-remote origin` — run from a non-repo dir so that lookup fails fast
    # and deterministically offline before the POSTMERGE seam is consulted.
    cd "$TMP" || return 1

    # Host seam: <op> <pr>. Fingerprint observations are complete by default and
    # can be replaced independently to model a single material transition.
    cp "$BATS_TEST_DIRNAME/../fixtures/pr_merge_loop/seam.sh" "$TMP/seam.sh" ||
        return 1
    chmod +x "$TMP/seam.sh"
    export PR_MERGE_LOOP_GH_CMD="$TMP/seam.sh"
    export PR_MERGE_LOOP_CLOCK_CMD="$TMP/clock.sh"
    cat > "$TMP/clock.sh" << 'EOF'
#!/usr/bin/env bash
echo "2026-09-19T00:00:00Z"
EOF
    chmod +x "$TMP/clock.sh"

    # loop_lock seam (file-backed) so cmd_tick can acquire/release offline.
    export LOOP_LOCK_DIR="$TMP/locks"
    export LOOP_LOCK_SETTLE_SEC=0.01 # this suite doesn't exercise the race window itself
    # post-merge-check seam: main CI green by default so cmd_signals reports
    # main_ci=green (a red seam is exported per-test to exercise halt).
    cat > "$TMP/pmc-green.sh" << 'EOF'
#!/usr/bin/env bash
echo '["success"]'
EOF
    chmod +x "$TMP/pmc-green.sh"
    export PR_MERGE_LOOP_POSTMERGE_CMD="$TMP/pmc-green.sh"
    export SEAM_STATE="$TMP/labels"
    cat > "$TMP/lockseam.sh" << 'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; op="$1"; pr="$2"; owner="${3:-}"
pd="$d/$pr"; mkdir -p "$pd"
case "$op" in
  has)
    newest="" ; shopt -s nullglob
    for f in "$pd"/*; do o="$(basename "$f")"; [ -z "$newest" ] || [[ "$o" > "$newest" ]] && newest="$o"; done
    [ -n "$newest" ] || exit 1
    printf '%s\t%s\n' "${SEAM_AGE:-0}" "$newest"
    exit 0 ;;
  add)
    [ -n "$owner" ] || exit 1
    : > "$pd/$owner"
    exit 0 ;;
  remove) [ -n "$owner" ] && rm -f "$pd/$owner"; exit 0 ;;
esac
EOF
    chmod +x "$TMP/lockseam.sh"
    export LOOP_LOCK_LABEL_CMD="$TMP/lockseam.sh"

    cat > "$TMP/lockseam_degraded.sh" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  has) exit 1 ;;
  add) exit 1 ;;
  remove) exit 0 ;;
esac
EOF
    chmod +x "$TMP/lockseam_degraded.sh"

    # Verification-gate seam. It can fail or change the observed head during
    # dispatch, which exercises the post-dispatch external-transition guard.
    cat > "$TMP/gateseam.sh" << 'EOF'
#!/usr/bin/env bash
printf 'gate\n' >> "${SEAM_GATE_LOG:?}"
if [[ -n "${SEAM_GATE_NEW_HEAD:-}" ]]; then
  printf '%s\n' "$SEAM_GATE_NEW_HEAD" > "${SEAM_HEAD_DIR:?}/${SEAM_GATE_NEW_HEAD_PR:-5}"
fi
[[ "${SEAM_GATE_FAIL:-0}" != 1 ]] || exit 1
_d='{"tier1":{"passed":true},"tier2":{"concerns":[]},"verdict":"APPROVED"}'
echo "${SEAM_GATE:-$_d}"
EOF
    chmod +x "$TMP/gateseam.sh"
    export VERIFICATION_GATE_REVIEW_CMD="$TMP/gateseam.sh"
}

pr_merge_loop_teardown() { [[ -n "${TMP:-}" && -d "$TMP" ]] && rm -rf "$TMP"; }
field() { python3 -c "import json,sys;print(json.load(sys.stdin)[\"$1\"])"; }
action() { python3 -c 'import json,sys;print(json.load(sys.stdin)["action"])'; }
call_count() {
    python3 - "$1" "$SEAM_CALL_LOG" << 'PY'
import sys

op, path = sys.argv[1:3]
with open(path, encoding="utf-8") as handle:
    print(sum(1 for line in handle if line.split(maxsplit=1)[0] == op))
PY
}

gate_count() {
    python3 - "$SEAM_GATE_LOG" << 'PY'
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(sum(1 for line in handle if line.strip()))
PY
}

# The consecutive-empty counter is keyed on the derived repository scope
# (empty_count_<sha256(host\0owner_repo)>) — and the `empty-run` CLI itself
# fails closed on gitlab (no fp-scope), so the gitlab monitor tests read the
# file cmd_run_monitor maintains directly.
gitlab_scope_count_path() {
    python3 - "$PR_MERGE_LOOP_STATE_DIR" << 'PY'
import hashlib
import os
import sys

h = hashlib.sha256("gitlab.com\0acme/widgets".encode()).hexdigest()
print(os.path.join(sys.argv[1], "empty_count_" + h))
PY
}

fingerprint_state() {
    python3 - "$PR_MERGE_LOOP_STATE_DIR" << 'PY'
import glob
import os
import sys

paths = glob.glob(os.path.join(sys.argv[1], "fp_*.json"))
assert len(paths) == 1, paths
print(paths[0])
PY
}

make_race_lock_seam() {
    cat > "$TMP/race-lockseam.sh" << 'EOF'
#!/usr/bin/env bash
d="${SEAM_STATE:?}"; op="$1"; pr="$2"; owner="${3:-}"; pd="$d/$pr"; mkdir -p "$pd"
case "$op" in
  has)
    newest="" ; shopt -s nullglob
    for f in "$pd"/*; do newest="$(basename "$f")"; done
    [ -n "$newest" ] || exit 1
    printf '0\t%s\n' "$newest" ;;
  add)
    cp "${RACE_STATE:?}" "${RACE_DEST:?}"
    [[ -z "${RACE_HEAD:-}" ]] || printf '%s\n' "$RACE_HEAD" > "${SEAM_HEAD_DIR:?}/$pr"
    : > "$pd/$owner" ;;
  remove) rm -f "$pd/$owner" ;;
esac
EOF
    chmod +x "$TMP/race-lockseam.sh"
}
