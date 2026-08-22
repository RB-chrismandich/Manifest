#!/usr/bin/env bash
# check_fresh_checkout.sh — FRESH-CHECKOUT gate for the vendored
# plugins/manifest-forge/runtime/bin/pr_merge_loop.sh bundle.
#
# Usage: check_fresh_checkout.sh [--help]
#   Exit 0 = every exercised subcommand (--help, merge, list-managed, signals,
#   tick) behaved as expected in a fresh `git archive`/`git write-tree`
#   checkout; exit 1 = a check failed (see stderr for which one).
#
#   Seam: FRESH_CHECKOUT_TREE_DIR, if set, is tested in place of a fresh
#   extraction (and is left on disk) — lets a caller pre-mutate an extracted
#   tree (e.g. delete one vendored file) and re-run this exact gate.
#
# CDDL QA-critic finding (2026-08-20): an earlier ad-hoc version of this gate
# exercised only `--help` and `merge` — the two subcommands that never touch
# loop_lock.sh, merge_decision.sh, verification_gate.sh, or pr_merge_loop_gh.sh.
# The critic proved this empirically: deleting those files from a fresh
# archive left both `--help` and `merge` passing (a "gate" that never fails is
# worth nothing). This version also exercises list-managed/signals/tick, using
# the same offline stub/seam pattern tests/bats/pr_merge_loop.bats already
# uses for gh/glab (no network calls, no real gh/glab invocations).
#
# The script under test is run by ABSOLUTE PATH from a $PWD that is neither
# the fresh checkout nor the original repo, so a relative-path (or $PWD-
# coincidence) reach-back into the original checkout cannot masquerade as
# self-containment — only SCRIPT_DIR-relative resolution inside the fresh
# checkout can make this pass.
set -euo pipefail

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "check-fresh-checkout: $*" >&2; else printf '%s\n' "check-fresh-checkout: $*" >&2; fi; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# FINDING 3(a) FIX (2026-08-20): a bundle installs independently (spec:
# docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md, Phase 1
# item 1.4) — a real plugin-only user gets ONLY plugins/manifest-forge/, never
# the rest of this monorepo. Extracting the whole `git write-tree` here made
# every monorepo path present in the "fresh checkout", so an undeclared
# repo-relative dependency (a `../../configs/...` reach-back, a sibling
# bundle's file) would silently resolve and escape detection entirely — this
# gate proved nothing about isolation, only about the script's own syntax.
# Narrow the extraction to the bundle directory under test: every dependency
# `pr_merge_loop.sh` and everything it calls actually needs (loop_lock.sh,
# merge_decision.sh, verification_gate.sh, pr_merge_loop_gh.sh, git_ops.sh,
# git_platform.sh, audit_log.sh, lifecycle.sh, runtime/config/*.json) is
# declared, machine-readably, in manifest-capabilities.yml's
# `components.runtime` list (forge-bin/forge-python/forge-config/
# forge-references, each a path INSIDE plugins/manifest-forge/) — none of it
# reaches outside the bundle. If a future change needs something the bundle
# does not carry, that dependency must be added under
# plugins/manifest-forge/ (declared in manifest-capabilities.yml) rather than
# assumed present from the surrounding monorepo; this extraction boundary is
# what makes an undeclared reach-back fail loudly instead of passing silently.
BUNDLE_PATH="plugins/manifest-forge"
OWN_TREE=1
if [[ -n "${FRESH_CHECKOUT_TREE_DIR:-}" ]]; then
    T="$FRESH_CHECKOUT_TREE_DIR"
    OWN_TREE=0
else
    T="$(mktemp -d "${TMPDIR:-/tmp}/fresh_checkout.XXXXXX")"
    git archive "$(git write-tree)" -- "$BUNDLE_PATH" | tar -x -C "$T"
fi
SEAMS="$(mktemp -d "${TMPDIR:-/tmp}/fresh_checkout_seams.XXXXXX")"
RUNDIR="$(mktemp -d "${TMPDIR:-/tmp}/fresh_checkout_run.XXXXXX")"
cleanup() {
    [[ "$OWN_TREE" -eq 1 ]] && rm -rf "$T"
    rm -rf "$SEAMS" "$RUNDIR"
}
trap cleanup EXIT

SCRIPT="$T/plugins/manifest-forge/runtime/bin/pr_merge_loop.sh"
BIN_DIR="$T/plugins/manifest-forge/runtime/bin"

fail=0

# FINDING 3(b) FOLLOW-UP FIX (2026-08-20, coordinator mutation-test finding):
# the `tick` behavioral assertions further down cannot, by themselves, prove
# every dependency is present. Concretely: deleting verification_gate.sh from
# the bundle and re-running still PASSED. Root cause — cmd_tick's run-gate
# branch is `gate="$("${SCRIPT_DIR}/verification_gate.sh" review "$pr" 2>/dev/null)"
# || gate='{"reviewer_error":true}'`. Whether verification_gate.sh (a) runs
# and honestly reports reviewer_error because no reviewer is configured
# (Finding 3(b)'s fix), or (b) does not exist at all so the invocation itself
# fails, the caught fallback JSON is IDENTICAL, so both paths reach
# `hand-human` — the exact "honest-looking outcome that is not discriminating"
# defect class this whole gate exists to catch, one level down. Mutating
# loop_lock.sh already WAS discriminating (a missing file makes the `acquire`
# call fail with an untrapped exit status that lands in cmd_tick's `*)`
# "locked — skipping" branch — distinct text from the present-and-degraded
# "cross-host lease unavailable" case), which is why that one mutation alone
# did not surface this.
#
# Fix (option 3 of the three offered — chosen because it generalizes to every
# dependency at once, rather than requiring a new distinguishing string to be
# hunted down per file, which is exactly how this defect was missed the first
# time): assert every file `pr_merge_loop.sh` and its callees reference via
# `${SCRIPT_DIR}/...` is present and executable in $T BEFORE running any
# subcommand. A missing dependency now fails on its own explicit, named check
# — never inferred from a downstream string that a different failure mode can
# also produce. This does not replace the behavioral assertions below (which
# still prove the present files are genuinely REACHED, not merely present);
# it closes the gap they cannot cover.
#
# List derived from docs/superpowers/specs/2026-08-19-marketplace-restructure-
# design.md §4 Phase 1 item 1.3 ("It is now five files" — pr_merge_loop.sh,
# merge_decision.sh, loop_lock.sh, verification_gate.sh, pr_merge_loop_gh.sh —
# "their remaining dependencies, git_ops.sh/git_platform.sh/audit_log.sh, are
# already present in runtime/bin") and confirmed by grepping every
# `${SCRIPT_DIR}/*.sh` reference in each of those files. lifecycle.sh is
# deliberately EXCLUDED: pr_merge_loop.sh references it, but only inside
# lifecycle_gate_ok's fail-open short-circuit (LIFECYCLE_TRACK_FOR_PR_CMD is
# unset in this test), so it is never actually invoked on the path this gate
# exercises — listing it here would assert a dependency this run does not
# genuinely require, the same over-claiming this fix exists to eliminate.
#
# Two lists, not one: every entry below is directly EXECUTED (invoked as
# `"${SCRIPT_DIR}/x.sh" args`, or `bash "${SCRIPT_DIR}/x.sh"` for
# git_platform.sh) and so must carry the executable bit `git archive`
# preserves from this repo's tracked mode — except pr_merge_loop_gh.sh, which
# `pr_merge_loop.sh` pulls in with `source`, not exec. A `source`d file only
# needs to exist and be readable; asserting `-x` on it would fail against its
# own correct, intentionally non-executable mode (confirmed against this
# repo: `ls -la runtime/bin/lib/pr_merge_loop_gh.sh` is `-rw-r--r--`, every
# other entry below is `-rwxr-xr-x`) — exactly the kind of false failure a
# pre-flight check must not introduce while fixing a false pass.
REQUIRED_EXEC_DEPS=(
    pr_merge_loop.sh
    merge_decision.sh
    verification_gate.sh
    loop_lock.sh
    git_ops.sh
    git_platform.sh
    audit_log.sh
)
REQUIRED_SOURCED_DEPS=(
    lib/pr_merge_loop_gh.sh
)
for dep in "${REQUIRED_EXEC_DEPS[@]}"; do
    depfile="$BIN_DIR/$dep"
    if [[ ! -f "$depfile" ]]; then
        err "FAIL: declared runtime dependency missing from bundle: $dep"
        fail=1
    elif [[ ! -x "$depfile" ]]; then
        err "FAIL: declared runtime dependency not executable: $dep"
        fail=1
    fi
done
for dep in "${REQUIRED_SOURCED_DEPS[@]}"; do
    depfile="$BIN_DIR/$dep"
    if [[ ! -f "$depfile" ]]; then
        err "FAIL: declared runtime dependency missing from bundle: $dep"
        fail=1
    elif [[ ! -r "$depfile" ]]; then
        err "FAIL: declared runtime dependency not readable: $dep"
        fail=1
    fi
done

# --- seams (mirrors tests/bats/pr_merge_loop.bats's setup(); offline, no
# network, no real gh/glab). ---
cat > "$SEAMS/gh_seam.sh" << 'EOF'
#!/usr/bin/env bash
case "$1" in
    list) echo "${SEAM_LIST:-[]}" ;;
    checks) printf '%s\n' ${SEAM_BUCKETS-pass} ;;
    reviewdecision) echo "${SEAM_RD:-APPROVED}" ;;
    unresolved-human) echo "${SEAM_UH:-0}" ;;
    disposition) echo "${SEAM_DISP:-merge}" ;;
    mergeable) echo "${SEAM_MRG:-MERGEABLE CLEAN}" ;;
    verify) echo "${SEAM_VERIFY:-pass}" ;;
    hold) echo "${SEAM_HOLD:-false}" ;;
    author) echo "${SEAM_AUTHOR:-Copilot}" ;;
    admin-check) echo "${SEAM_ADMIN:-true}" ;;
    protection) echo "${SEAM_PROT:-enforce_admins=false required_signatures=false merge_queue=false}" ;;
    update-branch) echo updated ;;
    do-merge) [ "${SEAM_MERGE_FAIL:-0}" = 1 ] && exit 1 || echo merged ;;
    headsha) echo "${SEAM_HEAD:-sha1}" ;;
    basebranch) echo "${SEAM_BASE:-main}" ;;
    mergecommit) echo "${SEAM_MERGE_SHA:-mergesha1}" ;;
esac
EOF
chmod +x "$SEAMS/gh_seam.sh"

# Faithful lock-label seam (same CDDL finding pr_merge_loop.bats/loop_lock.bats
# encode): a real GitHub `--add-label` only attaches a PRE-PROVISIONED label —
# labels.yml provisions only the static "loop-active", never the dynamic
# "loop-active:<epoch>:<owner>" lease name loop_lock.sh actually requests — so
# `add` MUST reject, always. `has`/`remove` operate on a real (pr, owner)
# lease-file layout.
cat > "$SEAMS/lock_seam.sh" << 'EOF'
#!/usr/bin/env bash
d="${SEAM_LOCK_STATE:?}"
op="$1"
pr="$2"
owner="${3:-}"
pd="$d/$pr"
mkdir -p "$pd"
case "$op" in
    has)
        newest=""
        shopt -s nullglob
        for f in "$pd"/*; do
            o="$(basename "$f")"
            [ -z "$newest" ] || [[ "$o" > "$newest" ]] && newest="$o"
        done
        [ -n "$newest" ] || exit 1
        printf '%s\t%s\n' "${SEAM_AGE:-0}" "$newest"
        exit 0
        ;;
    add) exit 1 ;;
    remove)
        [ -n "$owner" ] && rm -f "$pd/$owner"
        exit 0
        ;;
esac
EOF
chmod +x "$SEAMS/lock_seam.sh"

# FINDING 3(b) FIX (2026-08-20): no gate_seam.sh here, and VERIFICATION_GATE_
# REVIEW_CMD is deliberately left UNSET. verification_gate.sh's own header
# documents why: "this portable bundle ships no default reviewer command...
# unset behaves like an unresolvable seam and fails closed via reviewer_error"
# — a real plugin-only install (no bootstrap-deployed coordinator CLI) has
# this var unset too, always, by that same design. Injecting a reviewer here
# exercised a happy path (`run-gate` -> pass -> real merge attempt) that is
# UNREACHABLE for an actual user: unset, the real degraded outcome is
# `reviewer_error` -> `hand-human` (see merge_decision.sh). Asserting the
# happy path was itself the defect (it required a test-only environment seam
# that ships with no install); assert the real degraded behavior instead.

export PR_MERGE_LOOP_STATE_DIR="$SEAMS/state"
export PR_MERGE_LOOP_GH_CMD="$SEAMS/gh_seam.sh"
export LOOP_LOCK_DIR="$SEAMS/locks"
export LOOP_LOCK_SETTLE_SEC=0.01
export SEAM_LOCK_STATE="$SEAMS/labels"
export LOOP_LOCK_LABEL_CMD="$SEAMS/lock_seam.sh"
export PR_MERGE_LOOP_APPLY=0

# NOTE: `fail` is intentionally NOT reset here — it was declared (0) before
# the dependency pre-flight check above and must carry that check's result
# (a missing dependency must not be silently forgotten by the time the
# subcommand assertions below run).
out="" # populated indirectly by run_capture's `printf -v` — declared here so
# static analysis (and `set -u`) see it as assigned before first use.

# run_capture VAR CMD... — sets $VAR (stdout+stderr) and RC, without tripping
# THIS script's own `set -e`: a bare `x=$(cmd)` assignment is NOT exempt from
# errexit, only the condition of if/while/&&/|| is — so the substitution runs
# inside an explicit `if`.
run_capture() {
    local __var="$1"
    shift
    local __out
    if __out="$("$@" 2>&1)"; then
        RC=0
    else
        RC=$?
    fi
    printf -v "$__var" '%s' "$__out"
}

expect_contains() { # expect_contains LABEL NEEDLE HAYSTACK
    if [[ "$3" != *"$2"* ]]; then
        err "FAIL: $1 — expected output to contain: $2"
        printf '%s\n' "$3" | sed 's/^/    | /' >&2
        fail=1
    fi
}
expect_absent() { # expect_absent LABEL NEEDLE HAYSTACK
    if [[ "$3" == *"$2"* ]]; then
        err "FAIL: $1 — output must NOT contain: $2"
        printf '%s\n' "$3" | sed 's/^/    | /' >&2
        fail=1
    fi
}
expect_rc() { # expect_rc LABEL EXPECTED ACTUAL
    if [[ "$2" != "$3" ]]; then
        err "FAIL: $1 — exited $3, expected $2"
        fail=1
    fi
}

# Invoked from a THIRD directory — neither $T nor $REPO_ROOT — so a
# relative-path (or $PWD-coincidence) reach-back into the original checkout
# cannot pass this gate; only SCRIPT_DIR-relative resolution inside $T can.
cd "$RUNDIR"

run_capture out "$SCRIPT" --help
expect_rc "--help" 0 "$RC"
expect_contains "--help" "Usage: pr_merge_loop.sh" "$out"

run_capture out env PR_MERGE_LOOP_APPLY=1 "$SCRIPT" merge 1
expect_rc "merge" 78 "$RC"
expect_contains "merge" "automated merge is disabled" "$out"

run_capture out env SEAM_LIST='[{"number":1,"author":{"login":"Copilot","__typename":"Bot"}},{"number":2,"author":{"login":"some-human"}}]' \
    "$SCRIPT" list-managed
expect_rc "list-managed" 0 "$RC"
printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert [p["number"] for p in d] == [1], d' ||
    {
        err "FAIL: list-managed — did not filter to the automation-authored PR"
        fail=1
    }

run_capture out env SEAM_BUCKETS="pass pass" "$SCRIPT" signals 5
expect_rc "signals" 0 "$RC"
printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["checks"] == "PASS", d' ||
    {
        err "FAIL: signals — did not classify checks as PASS"
        fail=1
    }

# tick: default seam values are cheap-clear (checks PASS, disp merge,
# mergeable MERGEABLE CLEAN, hold false) -> run-gate -> verification_gate.sh
# runs for REAL (not seamed) with no reviewer configured -> reviewer_error ->
# hand-human (Finding 3(b): the actual behavior a plugin-only user gets, not
# an injected happy path). This single call still chains through
# loop_lock.sh (the degraded-lease path — our lock seam's `add` always
# rejects, matching real GitHub without a pre-provisioned dynamic label),
# merge_decision.sh (both the pre-gate and post-gate `decide` calls), and
# verification_gate.sh (the run-gate branch, genuinely invoked) — the four
# dependencies `--help`/`merge` alone never reach.
run_capture out "$SCRIPT" tick 1
expect_rc "tick" 0 "$RC"
expect_contains "tick (loop_lock.sh reached)" "cross-host lease unavailable" "$out"
expect_absent "tick (loop_lock.sh reached)" "locked — skipping" "$out"
expect_contains "tick (verification_gate.sh reached, no reviewer configured -> honest degrade)" "hand-human" "$out"
expect_absent "tick (merge never dispatched without a real reviewer)" "automated merge is disabled" "$out"

if [[ "$fail" -eq 0 ]]; then
    printf 'check-fresh-checkout: PASS (all %d declared runtime dependencies present+executable; help_exit=0 merge_exit=78; list-managed/signals reached; tick reached loop_lock.sh, merge_decision.sh, verification_gate.sh, pr_merge_loop_gh.sh and correctly degraded to hand-human with no reviewer configured)\n' "$((${#REQUIRED_EXEC_DEPS[@]} + ${#REQUIRED_SOURCED_DEPS[@]}))"
fi
exit "$fail"
