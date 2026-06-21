# #361 Auto-Dev Merge-Loop — Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 6 remaining #361 tasks — give the merge loop a hard wall-clock ceiling in code, wire the real fail-closed review-thread accessor, add the missing tests, and reconcile docs/tasks.

**Architecture:** `pr_merge_loop.sh` already has the per-PR primitives (`tick`, `signals`, `merge`, `empty-run`, `list-managed`) and a pure decision core (`merge_decision.sh`). We add a thin `run` subcommand that loops those primitives under a wall-clock deadline (via an injectable clock seam) with explicit exit codes, replace the `unresolved-human` stub with a real GraphQL query that fails closed and respects the bot allowlist, add per-network-call timeouts so a hang can't bust the ceiling, then add the test coverage and reconcile SKILL.md / tasks.md to match.

**Tech Stack:** Bash (`set -euo pipefail`), `gh` CLI (REST + GraphQL), Python 3 (inline classifiers/parsers), bats (offline, seam-injected tests), `shellcheck`, `yamllint`.

## Global Constraints

- Error output through `err() { echo "pr-merge-loop: $*" >&2; }` — already defined; route all errors/warnings through it (repo Script Conventions).
- Every user-facing entry point handles `--help` (already does via `usage`).
- The merge is the only irreversible action; **fail closed** everywhere — missing/ambiguous input must never produce a merge.
- All offline tests inject behavior through seams (`PR_MERGE_LOOP_GH_CMD`, `PR_MERGE_LOOP_STATE_DIR`, `LOOP_LOCK_LABEL_CMD`, `VERIFICATION_GATE_REVIEW_CMD`); tests must run with no network.
- Bot allowlist lives in `configs/claude/config/automation_authors.yml` (`authors:` list) — read it, never hardcode logins.
- New `run` loop: ceiling reached / 5-empty → exit `0`; `halt` (main red post-merge) → exit `11`.
- Default ceiling `PR_MERGE_LOOP_CEILING_SEC=600`; default inter-pass poll `PR_MERGE_LOOP_POLL_SEC=30`; clock via `PR_MERGE_LOOP_NOW_CMD` seam.

---

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `configs/claude/scripts/pr_merge_loop.sh` | loop orchestration + signals + merge | Modify: add `_now`, `_net`, `cmd_run`, real `count_unresolved_human`, dispatch + usage/header |
| `tests/bats/pr_merge_loop.bats` | offline seamed tests | Modify: add `run`/ceiling/empty-run, review-thread parser, address-cycle cases |
| `.skillshare/skills/auto-issue-dev/SKILL.md` | loop-control prose (T028) | Modify: call `run` instead of re-describing the loop |
| `specs/361-auto-dev-merge-loop/tasks.md` | task tracking | Modify: check off T004/T011/T024/T026; T003/T034 notes |
| `docs/COMMANDS.md` | command reference | Modify: document `run` subcommand (if merge-loop section exists) |

---

## Task 1: `run` loop driver with hard ceiling + per-call timeout (T026 + T024)

**Files:**
- Modify: `configs/claude/scripts/pr_merge_loop.sh`
- Test: `tests/bats/pr_merge_loop.bats`

**Interfaces:**
- Consumes: `cmd_list_managed`, `cmd_tick` (prints final action: `merge|revise|wait|update-branch|hand-human|halt|skip`), `cmd_empty_run get|incr|reset`.
- Produces: `cmd_run` (subcommand `run`); `_now()` → epoch seconds (seam `PR_MERGE_LOOP_NOW_CMD`); `_net <cmd...>` → runs under `timeout`/`gtimeout` if present (env `GH_NET_TIMEOUT`, default 60).

- [ ] **Step 1: Write the failing tests**

Append to `tests/bats/pr_merge_loop.bats`:

```bash
# --- T026: run loop driver + hard ceiling ---
@test "run: _net passes through and returns command output" {
    run "$SCRIPT" _net echo hi
    [ "$status" -eq 0 ]; [ "$output" = "hi" ]
}

@test "run: ceiling already past -> zero passes, no merge, exit 0" {
    # now-seam: first call (start)=0, every later call huge -> deadline gate trips immediately
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
c="${TMP:?}/nowc"; n=$(( $( [ -f "$c" ] && cat "$c" || echo 0 ) + 1 )); echo "$n" > "$c"
[ "$n" -le 1 ] && echo 0 || echo 999999
EOF
    chmod +x "$TMP/now.sh"
    export PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh" TMP PR_MERGE_LOOP_CEILING_SEC=10 PR_MERGE_LOOP_POLL_SEC=0
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [[ "$output" != *"merged"* ]]
}

@test "run: fully-idle passes increment empty-run and stop at 5" {
    export SEAM_LIST='[]' PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "5" ]
}

@test "run: an in-flight (waiting) PR resets the empty-run counter" {
    "$SCRIPT" empty-run incr; "$SCRIPT" empty-run incr; "$SCRIPT" empty-run incr; "$SCRIPT" empty-run incr
    [ "$("$SCRIPT" empty-run get)" = "4" ]
    # now-seam: plenty of zeros (>=1 pass) then sticky-huge to exit
    cat > "$TMP/now.sh" <<'EOF'
#!/usr/bin/env bash
c="${TMP:?}/nowc"; n=$(( $( [ -f "$c" ] && cat "$c" || echo 0 ) + 1 )); echo "$n" > "$c"
[ "$n" -le 8 ] && echo 0 || echo 999999
EOF
    chmod +x "$TMP/now.sh"
    export PR_MERGE_LOOP_NOW_CMD="$TMP/now.sh" TMP PR_MERGE_LOOP_CEILING_SEC=10 PR_MERGE_LOOP_POLL_SEC=0
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]' SEAM_BUCKETS="pending"
    run "$SCRIPT" run
    [ "$status" -eq 0 ]
    [ "$("$SCRIPT" empty-run get)" = "0" ]
}

@test "run: halt action propagates exit 11" {
    # gate passes + clean signals -> merge; force post-merge main RED so tick returns halt
    export SEAM_LIST='[{"number":5,"author":{"login":"Copilot","__typename":"Bot"}}]'
    export PR_MERGE_LOOP_APPLY=1 SEAM_MERGE_FAIL=0 PR_MERGE_LOOP_POLL_SEC=0 PR_MERGE_LOOP_CEILING_SEC=600
    # post-merge-check reads gh api directly; seam it to red via a check-runs override
    cat > "$TMP/pmc.sh" <<'EOF'
#!/usr/bin/env bash
echo '["failure"]'
EOF
    chmod +x "$TMP/pmc.sh"
    export PR_MERGE_LOOP_POSTMERGE_CMD="$TMP/pmc.sh"
    run "$SCRIPT" run
    [ "$status" -eq 11 ]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats tests/bats/pr_merge_loop.bats -f "run:"`
Expected: FAIL — `_net`/`run`/`PR_MERGE_LOOP_POSTMERGE_CMD` do not exist yet (unknown subcommand exit 64; halt test cannot reach 11).

- [ ] **Step 3: Add the clock + network seams and a post-merge seam hook**

In `pr_merge_loop.sh`, after the `err()` definition (around line 22), add:

```bash
# Injectable clock (tests fast-forward via PR_MERGE_LOOP_NOW_CMD) and a bounded
# network wrapper so a single hung call can never bust the hard ceiling.
_now() { if [[ -n "${PR_MERGE_LOOP_NOW_CMD:-}" ]]; then "${PR_MERGE_LOOP_NOW_CMD}"; else date +%s; fi; }
_net() {
    local t="${GH_NET_TIMEOUT:-60}"
    if   command -v timeout  >/dev/null 2>&1; then timeout  "$t" "$@"
    elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$t" "$@"
    else "$@"; fi
}
```

In `cmd_post_merge_check` (line 163), make the check-runs read seam-overridable so the loop's halt path is testable. Replace the body's `state=` line (line 166):

```bash
    if [[ -n "${PR_MERGE_LOOP_POSTMERGE_CMD:-}" ]]; then
        state="$("${PR_MERGE_LOOP_POSTMERGE_CMD}")"
    else
        state="$(_net gh api "repos/{owner}/{repo}/commits/${sha}/check-runs" -q '[.check_runs[]|.conclusion]' 2>/dev/null)"
    fi
```

(Keep the `sha=` line above it; when `PR_MERGE_LOOP_POSTMERGE_CMD` is set the `sha` read may fail — guard it: change the `sha=` line's failure branch to fall through when the seam is set:)

```bash
    sha="$(gh api "repos/{owner}/{repo}/commits/main" -q '.sha' 2>/dev/null)" \
        || { [[ -n "${PR_MERGE_LOOP_POSTMERGE_CMD:-}" ]] || { err "cannot read main sha — fail closed"; return 10; }; sha="seam"; }
```

- [ ] **Step 4: Implement `cmd_run`**

Add before `main()` (after `cmd_tick`, line 240):

```bash
# --- T026/T024: bounded self-paced loop driver. One merge in flight at a time
# (loop_lock, inside cmd_tick). Hard wall-clock ceiling; stops after 5 empty passes.
# Exit 0 = ceiling/5-empty (normal); exit 11 = halt (main red post-merge).
cmd_run() {
    local ceiling="${PR_MERGE_LOOP_CEILING_SEC:-600}" poll="${PR_MERGE_LOOP_POLL_SEC:-30}"
    local start deadline now managed pr act inflight n
    start="$(_now)"; deadline=$((start + ceiling))
    while :; do
        now="$(_now)"; (( now < deadline )) || break
        managed="$(cmd_list_managed | python3 -c \
            'import json,sys;print(" ".join(str(p["number"]) for p in json.load(sys.stdin)))' 2>/dev/null || echo "")"
        inflight=0
        # shellcheck disable=SC2086 # word-split the space-joined PR numbers (bash 3.2-safe)
        for pr in $managed; do
            now="$(_now)"; (( now < deadline )) || break
            act="$(cmd_tick "$pr")"
            case "$act" in
                halt) err "loop HALT — main breakage on #$pr"; return 11 ;;
                merge|revise|update-branch|wait|skip) inflight=1 ;;
            esac
        done
        if (( inflight == 1 )); then
            cmd_empty_run reset >/dev/null
        else
            n="$(cmd_empty_run incr)"
            (( n >= 5 )) && { err "5 consecutive empty runs — stopping"; break; }
        fi
        now="$(_now)"; (( now < deadline )) || break
        [[ "$poll" -gt 0 ]] && sleep "$poll"
    done
    return 0
}
```

- [ ] **Step 5: Wire dispatch, usage, header, and a `_net` test hook**

In `main()` add before the `*)` arm (after the `tick)` line 252):

```bash
        run)             cmd_run "$@"; exit $? ;;
        _net)            _net "$@"; exit $? ;;
```

In `usage()` (heredoc, after the `tick` line 37) add:

```
  run [--apply]                Self-paced bounded loop (10-min ceiling; stop at 5 empty).
```

In the top comment block, add to the subcommand list (after line 14) `#   run                     Bounded self-paced loop (ceiling + 5-empty stop).` and to the Seams line add `PR_MERGE_LOOP_NOW_CMD`, `PR_MERGE_LOOP_CEILING_SEC`, `PR_MERGE_LOOP_POLL_SEC`, `GH_NET_TIMEOUT`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `bats tests/bats/pr_merge_loop.bats -f "run:"`
Expected: PASS (5 new tests).

- [ ] **Step 7: Run the full suite + shellcheck**

Run: `bats tests/bats/pr_merge_loop.bats && shellcheck configs/claude/scripts/pr_merge_loop.sh`
Expected: all green; shellcheck clean (every `cmd_run` var is `local`).

- [ ] **Step 8: Commit**

```bash
git add configs/claude/scripts/pr_merge_loop.sh tests/bats/pr_merge_loop.bats
git commit -S -m "feat(scripts): bounded run loop with hard ceiling + per-call timeout (#361 T026/T024)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: real fail-closed review-thread accessor (T004)

**Files:**
- Modify: `configs/claude/scripts/pr_merge_loop.sh`
- Test: `tests/bats/pr_merge_loop.bats`

**Interfaces:**
- Consumes: `AUTHORS_FILE` (module var, line 26), `_net` (Task 1), `PR_MERGE_LOOP_THREADS_JSON` seam.
- Produces: `count_unresolved_human <pr>` → integer count of **human-authored** unresolved, non-outdated review threads; fails closed (`1`) on any error/malformed payload. Exposed as internal subcommand `count-unresolved-human` for offline tests. `gh_op unresolved-human` now calls it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/bats/pr_merge_loop.bats`:

```bash
# --- T004: real review-thread accessor (fail-closed, allowlist-aware) ---
THREADS='{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[%s]}}}}}'

@test "threads: unresolved human thread -> count 1" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "1" ]
}
@test "threads: unresolved BOT thread is advisory -> count 0" {
    node='{"isResolved":false,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"coderabbitai"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$status" -eq 0 ]; [ "$output" = "0" ]
}
@test "threads: resolved thread -> count 0" {
    node='{"isResolved":true,"isOutdated":false,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "0" ]
}
@test "threads: outdated unresolved thread -> count 0" {
    node='{"isResolved":false,"isOutdated":true,"comments":{"nodes":[{"author":{"login":"some-human"}}]}}'
    PR_MERGE_LOOP_THREADS_JSON="$(printf "$THREADS" "$node")" run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "0" ]
}
@test "threads: malformed payload fails closed -> count 1" {
    PR_MERGE_LOOP_THREADS_JSON="not json at all" run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "1" ]
}
@test "threads: missing nodes key fails closed -> count 1" {
    PR_MERGE_LOOP_THREADS_JSON='{"data":{"repository":{"pullRequest":{}}}}' run "$SCRIPT" count-unresolved-human 5
    [ "$output" = "1" ]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bats tests/bats/pr_merge_loop.bats -f "threads:"`
Expected: FAIL — `count-unresolved-human` is an unknown subcommand (exit 64).

- [ ] **Step 3: Implement the accessor + parser**

In `pr_merge_loop.sh`, add after `gh_op` (line 79):

```bash
# Raw review-thread JSON for a PR. Seam: PR_MERGE_LOOP_THREADS_JSON (offline tests).
gh_threads_raw() {
    if [[ -n "${PR_MERGE_LOOP_THREADS_JSON:-}" ]]; then printf '%s' "$PR_MERGE_LOOP_THREADS_JSON"; return 0; fi
    local pr="${1:?pr required}" nwo owner repo
    nwo="$(_net gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" || return 1
    owner="${nwo%%/*}"; repo="${nwo##*/}"
    _net gh api graphql -F owner="$owner" -F repo="$repo" -F pr="$pr" -f query='
      query($owner:String!,$repo:String!,$pr:Int!){
        repository(owner:$owner,name:$repo){
          pullRequest(number:$pr){
            reviewThreads(first:100){
              nodes{ isResolved isOutdated comments(first:1){ nodes{ author{ login } } } }
            }}}}' 2>/dev/null
}

# Count HUMAN-authored unresolved, non-outdated review threads. Bot nits (allowlist)
# are advisory. Any error/malformed payload -> 1 (fail closed: a thread might block).
count_unresolved_human() {
    local raw; raw="$(gh_threads_raw "${1:?pr required}")" || { echo 1; return 0; }
    printf '%s' "$raw" | python3 - "$AUTHORS_FILE" <<'PY'
import json, sys
try:
    import yaml
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception:
    cfg = {}
bots = {a.lower().replace("[bot]", "") for a in (cfg.get("authors") or [])}
try:
    nodes = json.load(sys.stdin)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    if not isinstance(nodes, list):
        raise ValueError("nodes not a list")
except Exception:
    print(1); sys.exit(0)  # malformed -> fail closed
count = 0
for t in nodes:
    if t.get("isResolved") or t.get("isOutdated"):
        continue
    cs = ((t.get("comments") or {}).get("nodes") or [])
    login = ((cs[0].get("author") or {}).get("login") if cs else "") or ""
    if login.lower().replace("[bot]", "") in bots:
        continue  # advisory bot nit
    count += 1
print(count)
PY
}
```

In `gh_op` (line 66) replace the stub line:

```bash
        unresolved-human) count_unresolved_human "$pr" ;;
```

- [ ] **Step 4: Wire the test subcommand**

In `main()` add before `*)`:

```bash
        count-unresolved-human) count_unresolved_human "$@"; exit $? ;;
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `bats tests/bats/pr_merge_loop.bats -f "threads:"`
Expected: PASS (6 tests). Then confirm the existing seam test still passes:
Run: `bats tests/bats/pr_merge_loop.bats -f "unresolved human thread"`
Expected: PASS (classifier path via `SEAM_UH`, unchanged).

- [ ] **Step 6: shellcheck + commit**

```bash
shellcheck configs/claude/scripts/pr_merge_loop.sh
git add configs/claude/scripts/pr_merge_loop.sh tests/bats/pr_merge_loop.bats
git commit -S -m "feat(scripts): real fail-closed review-thread accessor (#361 T004)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: address-cycle coverage (T011)

**Files:**
- Test: `tests/bats/pr_merge_loop.bats`

**Interfaces:**
- Consumes: `cmd_address_cycle` (increments `${STATE_DIR}/rev_<pr>`), `cmd_signals`, `merge_decision.sh decide`, `MAX_REVISIONS`.
- Produces: none (test-only).

- [ ] **Step 1: Write the failing tests**

Append to `tests/bats/pr_merge_loop.bats`:

```bash
# --- T011: address-cycle increments revisions + budget exhaustion -> hand-human ---
@test "address-cycle increments revisions_used" {
    "$SCRIPT" address-cycle 5
    [ "$(cat "$PR_MERGE_LOOP_STATE_DIR/rev_5")" = "1" ]
    "$SCRIPT" address-cycle 5
    [ "$(cat "$PR_MERGE_LOOP_STATE_DIR/rev_5")" = "2" ]
}
@test "address-cycle: under budget with failing checks -> revise" {
    "$SCRIPT" address-cycle 5    # revisions_used=1
    sig="$(MAX_REVISIONS=3 SEAM_BUCKETS="pass fail" "$SCRIPT" signals 5)"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "revise" ]
}
@test "address-cycle: at budget with failing checks -> hand-human + needs-human" {
    "$SCRIPT" address-cycle 5; "$SCRIPT" address-cycle 5   # revisions_used=2
    sig="$(MAX_REVISIONS=2 SEAM_BUCKETS="pass fail" "$SCRIPT" signals 5)"
    run bash -c "echo '$sig' | '$DECIDE' decide"
    [ "$(echo "$output" | action)" = "hand-human" ]
    [ "$(echo "$output" | python3 -c 'import json,sys;print(json.load(sys.stdin)["label"])')" = "needs-human" ]
}
```

- [ ] **Step 2: Run to verify they pass (behavior already implemented)**

Run: `bats tests/bats/pr_merge_loop.bats -f "address-cycle"`
Expected: PASS — these lock the T013/T014 behavior. If any fails, the regression is real; fix the script, do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add tests/bats/pr_merge_loop.bats
git commit -S -m "test(scripts): address-cycle increment + budget exhaustion (#361 T011)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: reconcile SKILL.md, tasks.md, and docs (T026/T004 prose; T034 note)

**Files:**
- Modify: `.skillshare/skills/auto-issue-dev/SKILL.md`
- Modify: `specs/361-auto-dev-merge-loop/tasks.md`
- Modify: `docs/COMMANDS.md` (if a merge-loop section exists)

**Interfaces:** none (docs).

- [ ] **Step 1: Point SKILL.md loop-control at `run`**

In `.skillshare/skills/auto-issue-dev/SKILL.md`, replace the **"4. Loop control."** paragraph (the one describing empty-run reset/incr, 5-empty, one-merge-in-flight — around line 85) with:

```markdown
4. **Loop control.** Run one bounded pass with `pr_merge_loop.sh run` (set
   `PR_MERGE_LOOP_APPLY=1` for real merges; default dry-run). It self-paces, enforces a
   hard 10-minute ceiling, serializes merges via `loop_lock` (one in flight; monitoring
   interleaves — FR-014), resets the empty-run counter on work / increments on idle passes,
   and **stops after 5 consecutive empty runs** (FR-018/018a). It exits non-zero (11) if a
   merge reddens `main` (halt) so `/loop` surfaces the failure. `/loop /auto-issue-dev`
   remains the outer re-invoker that gives each pass fresh context.
```

- [ ] **Step 2: Check off completed tasks in tasks.md**

In `specs/361-auto-dev-merge-loop/tasks.md`, flip these lines from `- [ ]` to `- [x]`: **T004, T011, T024, T026**. For T004, also append to its line: `(wired inline in pr_merge_loop.sh as count_unresolved_human — accessors are co-located in gh_op rather than git_ops.sh; no other consumer, YAGNI).` For T026, append: `(implemented as the run subcommand; /loop is the outer re-invoker).`

- [ ] **Step 3: Add the T034 deferral note**

Replace the T034 line (`- [ ] T034 ...`) body, keeping it unchecked, with a note block beneath it:

```markdown
- [ ] T034 Run quickstart.md dry-run validation against a real managed PR — **DEFERRED**:
  no live PR exists yet (branch is local-only). Run after pushing the branch:
  ```bash
  gh pr create --base main --head 361-auto-dev-merge-loop \
    --title "feat: auto-dev merge loop (#361)" --body "Closes #361"
  configs/claude/scripts/pr_merge_loop.sh signals <PR> --json \
    | configs/claude/scripts/merge_decision.sh decide   # expect one {action}; no mutation
  gh pr view <PR>   # confirm no label/state change
  ```
  (`signals <pr>` works against any PR number even though `list-managed` skips human authors.)
```

- [ ] **Step 4: Document the `run` subcommand**

If `docs/COMMANDS.md` has an auto-issue-dev / merge-loop section, add a bullet for `pr_merge_loop.sh run [--apply]` (bounded self-paced loop, 10-min ceiling, stop-at-5, exit 11 on halt). If no such section exists, skip — do not invent one.

- [ ] **Step 5: Commit**

```bash
git add .skillshare/skills/auto-issue-dev/SKILL.md specs/361-auto-dev-merge-loop/tasks.md docs/COMMANDS.md
git commit -S -m "docs(specs): reconcile run-loop + review-thread design; defer T034 (#361)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: full verification gate (T032/T033 re-run)

**Files:** none (verification).

- [ ] **Step 1: shellcheck the three scripts**

Run: `shellcheck configs/claude/scripts/pr_merge_loop.sh configs/claude/scripts/merge_decision.sh configs/claude/scripts/loop_lock.sh`
Expected: no output (clean).

- [ ] **Step 2: yamllint edited YAML**

Run: `yamllint configs/claude/config/automation_authors.yml`
Expected: clean (file unchanged here, but confirm it parses for the new parser).

- [ ] **Step 3: full bats suite**

Run: `bats tests/bats/merge_decision.bats tests/bats/loop_lock.bats tests/bats/pr_merge_loop.bats`
Expected: all pass — prior 64 + the new `run`/`threads`/`address-cycle` cases.

- [ ] **Step 4: Commit (only if any fixup was needed)**

```bash
git add -A && git commit -S -m "chore(scripts): lint/test fixups for #361 completion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: live label provisioning (T003) — gated

**Files:** none (live mutation).

- [ ] **Step 1: Dry-run preview**

Run: `configs/claude/scripts/label_sync.sh --dry-run`
Expected: shows `[dry-run] Would create:` for any of `ready-to-merge` / `loop-active` / `hold` not yet present; `[exists]` for present ones. If all three already exist, it reports them as `[exists]` (effectively "No changes required").

- [ ] **Step 2: Present the diff and STOP for go-ahead**

Show the dry-run output to the user. **Do not proceed without explicit approval** — this mutates the live GitHub repo.

- [ ] **Step 3: Real sync (only after go-ahead)**

Run: `configs/claude/scripts/label_sync.sh`
Expected: the three new labels created/confirmed on the active platform.

- [ ] **Step 4: Mark T003 done**

In `specs/361-auto-dev-merge-loop/tasks.md`, flip T003 to `- [x]`. Commit:

```bash
git add specs/361-auto-dev-merge-loop/tasks.md
git commit -S -m "chore(labels): provision merge-loop labels (#361 T003)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage** (against `2026-06-20-361-merge-loop-completion-design.md`):
- T026 run + hard ceiling + exit codes (0 / 11) + per-call timeout → Task 1 ✓
- T024 empty-run accounting (in-flight reset, idle incr, stop-at-5) + clock-seam ceiling → Task 1 ✓
- T004 real GraphQL accessor, inline, fail-closed on malformed, allowlist from `automation_authors.yml` → Task 2 ✓
- T011 address-cycle increment + budget→hand-human → Task 3 ✓
- T003 dry-run → gated real sync → Task 6 ✓
- T034 deferred with concrete recipe → Task 4 ✓
- SKILL.md calls `run`; tasks.md reconciled → Task 4 ✓
- TDD ordering (tests fail first) → Tasks 1, 2 ✓ (Task 3 locks existing behavior, called out)
- shellcheck/`local` discipline + full suite green → Tasks 1, 5 ✓

**Placeholder scan:** no TBD/TODO; every code step shows full code; every test shows assertions.

**Type/name consistency:** `_now`, `_net`, `cmd_run`, `gh_threads_raw`, `count_unresolved_human`, seams `PR_MERGE_LOOP_NOW_CMD` / `PR_MERGE_LOOP_THREADS_JSON` / `PR_MERGE_LOOP_POSTMERGE_CMD` / `PR_MERGE_LOOP_CEILING_SEC` / `PR_MERGE_LOOP_POLL_SEC` / `GH_NET_TIMEOUT` used identically across impl and tests. `count-unresolved-human` subcommand matches the function. Action strings match `merge_decision.sh` output (`merge|revise|wait|update-branch|hand-human|halt`) plus `skip` from `cmd_tick`.
