# 24h Change-Set Validation & Live Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate every runnable change in the 24h set (`4643b72..0722b88`), fix any reds, back up and deploy to live
`~/.claude` via `bootstrap.sh`, then re-validate the deployed environment — with evidence at every step.

**Architecture:** A four-phase runbook (test → backup → deploy → re-validate) plus a fix-forward gate (A.5) and a
reconciliation step (D.5). Phase A runs against repo/tmp paths and must go green (fixing reds on-branch) before any live
overwrite. Phase B makes the deploy reversible. Phase C deploys. Phase D re-exercises only deploy-sensitive features
against `~/.claude`. D.5 opens a reviewable PR (never auto-merge).

**Tech Stack:** Bash (`lifecycle.sh`, `lint_on_edit_hook.sh`, `bootstrap/lib/*`, `check_status.sh`), Python 3 (ai-hooks
runtime, `smoke_test.py`, agents), bats, pytest, ruff, shellcheck, yamllint, markdownlint, `git`/`gh`.

## Global Constraints

- **Worktree (run everything here):** `/Users/chrismandich/Documents/GitHub/Manifest/.claude/worktrees/test-end-2-end`
- **Branch:** `worktree-test-end-2-end` (currently at `0722b88`, == `main`). All fix-forward commits land here.
- **Diff range under test:** `4643b72..0722b88` (10 commits, features 363–367 + bot opts).
- **Source-of-truth exercise matrix:** `docs/superpowers/specs/exercise-matrix-2026-06-29.json` (41 features). The
  design doc owns phase routing.

- **Do-it-right bias:** correctness/reversibility over speed. Never push a known-red state into live config. Fixes are
  TDD'd.

- **No auto-merge:** the fix-forward PR is the user's to merge (spec §6).
- **Fail-stop after live overwrite:** the moment a Phase C deploy step fails or a Phase D exercise reveals a broken live
  env, STOP, report with evidence, offer restore-from-backup. No ad-hoc fixes against live `~/.claude`.

- **Isolation env vars (Phase A/D):** never pollute real `~`. Use `export LIFECYCLE_STATE_DIR=$(mktemp -d)/state` for
  lifecycle state, `LIFECYCLE_SMOKE_CMD`/`LIFECYCLE_PROVIDERS_CONFIG` pointed at repo paths.

- **Run log:** append evidence per step to `<scratchpad>/run-log.md`; the absolute `<scratchpad>` path is
  defined in Task 0, Step 1.

- **Graphify CLI install is OUT OF SCOPE** (spec §7) unless the user opts in. Validate toggle plumbing, skill
  presence, and the "not installed" path only — do NOT run `uv tool install graphifyy`.

---

### Task 0: Run-log + start-state capture

**Files:**

- Create: `<scratchpad>/run-log.md`
- Create: `<scratchpad>/backup-manifest.txt` (written in Task B1; paths recorded here)

**Interfaces:**

- Produces: `SCRATCH` path, the recorded deployed SHA, and the pre-run existence map of backup paths (consumed by Task
  B1's PRESENT/ABSENT manifest).

- [ ] **Step 1: Define the scratchpad path and start the run log**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest/.claude/worktrees/test-end-2-end
SCRATCH="/private/tmp/claude-501/-Users-chrismandich-Documents-GitHub-Manifest--claude-worktrees-test-end-2-end/1f7d6653-ffb4-4f9a-8437-3f2f371c07ae/scratchpad"
mkdir -p "$SCRATCH"
{
  echo "# 24h Validation Run Log — $(git rev-parse --short HEAD)"
  echo "Range under test: 4643b72..0722b88"
  echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
} > "$SCRATCH/run-log.md"
cat "$SCRATCH/run-log.md"
```

Expected: run log created showing HEAD `0722b88`, branch `worktree-test-end-2-end`.

- [ ] **Step 2: Record the pre-run existence map of all backup-scope paths**

```bash
for p in "$HOME/.claude" "$HOME/.cursor/rules" "$HOME/.gemini" "$HOME/.codex" "$HOME/.antigravity" "$HOME/.manifest"; do
  if [ -e "$p" ]; then echo "PRESENT $p"; else echo "ABSENT $p"; fi
done | tee "$SCRATCH/pre-run-paths.txt"
```

Expected: a line per path tagged `PRESENT`/`ABSENT`. (`~/.manifest` is likely `ABSENT`; that drives the sentinel-restore
in Task B1.)

- [ ] **Step 3: Commit nothing yet — this is read-only state capture.** No git action.

---

## PHASE A — Baseline test (repo paths, before touching `~`)

### Task A1: Validate `pyproject.toml` / ruff config FIRST (backs three lint layers)

**Files:**

- Read: `pyproject.toml`
- Test: `tests/python/`

**Interfaces:**

- Produces: confirmation that the shared ruff/pytest config is sound, so A2's lint and A4's pytest are trustworthy.

- [ ] **Step 1: Confirm pyproject parses and shows the strict pytest flags**

```bash
python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(d['tool']['pytest']['ini_options'])"
```

Expected: a dict containing `testpaths` (`['tests/python']`) and `addopts` with `--strict-markers --strict-config`.

- [ ] **Step 2: Prove the strict-markers dependency does not break collection**

```bash
python3 -m pytest tests/python/ --collect-only -q 2>&1 | tail -3
```

Expected: collects (~400+ tests), exit 0, NO "unregistered marker" / "unknown config option" error. If it errors on the
`asyncio` marker, `pytest-asyncio` is missing — record as a Phase A red for A.5.

- [ ] **Step 3: Record result in run log**

```bash
echo "## A1 pyproject/ruff: PASS (collect-only clean)" >> "$SCRATCH/run-log.md"
```

### Task A2: CI-mirror lint (shellcheck, yamllint, markdownlint, ruff)

**Files:**

- Test: shell scripts, YAML configs, key docs, Python under the changed set.

- [ ] **Step 1: shellcheck the changed shell**

```bash
shellcheck configs/claude/scripts/lifecycle.sh configs/claude/scripts/lint_on_edit_hook.sh \
  configs/claude/scripts/check_status.sh configs/claude/scripts/pr_merge_loop.sh \
  configs/claude/scripts/spec_review.sh bootstrap.sh bootstrap/lib/*.sh; echo "rc=$?"
```

Expected: `rc=0` (no findings). Any finding → Phase A red.

- [ ] **Step 2: yamllint the config + key YAML**

```bash
yamllint configs/claude/config/command_config.yml configs/claude/config/lifecycle_providers.yml \
  configs/claude/config/services.yml configs/claude/config/command_categories.yml .pre-commit-config.yaml; echo "rc=$?"
```

Expected: `rc=0`.

- [ ] **Step 3: markdownlint the key docs (CI globs) + ruff the changed Python**

```bash
npx --yes markdownlint-cli@0.49.0 --config .markdownlint.jsonc AGENTS.md CLAUDE.md README.md docs/*.md; echo "md-rc=$?"
ruff check --no-fix .; echo "ruff-rc=$?"
```

Expected: both `rc=0`. (ruff uses the `pyproject.toml` config validated in A1.)

- [ ] **Step 4: Record result**

```bash
echo "## A2 lint mirror: PASS" >> "$SCRATCH/run-log.md"
```

### Task A3: bats suite + confirm the predicted `subagent_policy.bats` RED

**Files:**

- Test: `tests/bats/`

**Interfaces:**

- Produces: the confirmed list of failing bats suites (expected: `subagent_policy.bats`), consumed by Task A5.1.

- [ ] **Step 1: Run the full bats suite**

```bash
bats tests/bats/ 2>&1 | tail -30; echo "rc=${PIPESTATUS[0]}"
```

Expected: most suites pass; `subagent_policy.bats` FAILS on test 1 with
`smoke-orchestrator: no subagents disposition in tool_policies`. Record every failing suite.

- [ ] **Step 2: Isolate and confirm the expected failure with its exact message**

```bash
bats tests/bats/subagent_policy.bats 2>&1 | sed -n '1,20p'
```

Expected: `not ok 1 every skill has a subagents disposition (dynamic coverage)` with the offending line
`- smoke-orchestrator: no \`subagents\` disposition in tool_policies`. This is the known A.5 fix target.

- [ ] **Step 3: Record the bats inventory**

```bash
echo "## A3 bats: subagent_policy.bats RED (smoke-orchestrator) — confirmed; others: <list>" >> "$SCRATCH/run-log.md"
```

### Task A4: pytest suite (full run)

**Files:**

- Test: `tests/python/`

- [ ] **Step 1: Run the full python suite**

```bash
python3 -m pytest tests/python/ -q 2>&1 | tail -15; echo "rc=${PIPESTATUS[0]}"
```

Expected: all pass (matrix observed ~422 collected; graphify/config tests green). Any failure → Phase A red for A.5.

- [ ] **Step 2: Record result**

```bash
echo "## A4 pytest: <N> passed" >> "$SCRATCH/run-log.md"
```

### Task A5: lifecycle deep exercise — decision core, init, status/anchor, verdict, status-map, reconcile (tmp state)

**Files:**

- Test (exercise, not edit): `configs/claude/scripts/lifecycle.sh`, `configs/claude/config/lifecycle_providers.yml`

> Commands below are verbatim from the exercise matrix. Run each block; confirm the inline `# expected` comments. All
> state goes to a tmp dir — never `~/.manifest`.

- [ ] **Step 1: decide / gate (pure decision core)**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest/.claude/worktrees/test-end-2-end && SC=configs/claude/scripts/lifecycle.sh
$SC decide 'not json at all'    # garbage -> still exit 0, action=refuse
$SC decide '{"actor_mode":"agent","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'  # refuse, missing_prereq=spec_review_product
$SC decide '{"actor_mode":"human","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'  # warn
$SC gate '{"actor_mode":"agent","current_phase":"specify","phase_gate":{"gate_type":"artifact","present":true}}'; echo $?   # 0
$SC gate '{"actor_mode":"human","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}'; echo $?   # 3 (warn)
```

Expected: `decide` prints single-line JSON and exits 0 every time; `gate` exit codes are exactly 0/3/1 for
allow/warn/refuse. No Python traceback anywhere.

- [ ] **Step 2: init (provider detection + 0700/0600 state)**

```bash
SC=configs/claude/scripts/lifecycle.sh && export LIFECYCLE_STATE_DIR=$(mktemp -d)/state
for ep in 'PROJ-123' 'org/repo#42' 'https://github.com/acme/widgets/issues/42' 'https://gitlab.com/acme/widgets/-/issues/9' 'https://linear.app/team/issue/ENG-7' 'https://acme.atlassian.net/browse/ENG-44'; do $SC init "$ep"; done
$SC init 'garbage text'; echo "rc=$?"   # rc=2, no track
$SC init PROJ-123; echo "rc=$?"          # idempotent -> 'track exists', rc=0
stat -f '%Sp %N' "$LIFECYCLE_STATE_DIR" "$LIFECYCLE_STATE_DIR"/*.json
```

Expected: six init calls print correct `provider__entity`; garbage exits 2; re-init prints `track exists` rc=0; dir
`drwx------`, files `-rw-------`.

- [ ] **Step 3: status / anchor, verdict, status-map, reconcile**

Run the `status/anchor`, `verdict`, `status-map`, and `reconcile` blocks verbatim from the matrix
(`exercise-matrix-2026-06-29.json`, lifecycle cluster). For status-map/reconcile, first set
`export LIFECYCLE_PROVIDERS_CONFIG=$(pwd)/configs/claude/config/lifecycle_providers.yml`.

Expected (per matrix): status shows `phase: 1/9 specify`; `--json` round-trips `current_phase=specify`; missing track
exits 2; verdict maps `[]`/`NO_ISSUES`→APPROVED, CRITICAL→BLOCKED, LOW→NEEDS_REVIEW, garbage→BLOCKED; status-map
jira→`transition`, github→`label`, unknown→exit 2; reconcile prints `in sync`/`adopted`/`CONFLICT ... needs-human`
(rc=1) with no oscillation.

- [ ] **Step 4: Record result**

```bash
echo "## A5 lifecycle (decide/init/status/anchor/verdict/status-map/reconcile): PASS" >> "$SCRATCH/run-log.md"
```

### Task A6: lifecycle `advance` + smoke-backed Verify/Implement gates (HIGH risk)

**Files:**

- Test (exercise): `configs/claude/scripts/lifecycle.sh`, `configs/claude/scripts/smoke_test.py`

- [ ] **Step 1: Run the real-smoke advance flow (matrix, verbatim)**

```bash
SC=configs/claude/scripts/lifecycle.sh
export LIFECYCLE_STATE_DIR=$(mktemp -d)/state && export LIFECYCLE_SMOKE_CMD="python3 $(pwd)/configs/claude/scripts/smoke_test.py"
to_impl(){ for g in artifact artifact verdict artifact artifact verdict verdict; do [ "$g" = verdict ] && $SC advance "$1" --actor agent --gate '{"gate_type":"verdict","verdict":"APPROVED"}' >/dev/null || $SC advance "$1" --actor agent --gate '{"gate_type":"artifact","present":true}' >/dev/null; done; }
$SC init PROJ-200 >/dev/null && to_impl jira__PROJ-200
$SC subtask jira__PROJ-200 --id S1 --ship login >/dev/null
$SC advance jira__PROJ-200 --actor agent --unit billing; echo "rc=$?"   # MISSING smoke -> refuse rc=1, stays implement
$SC subtask jira__PROJ-200 --id S1 --exempt --reason 'no UI' >/dev/null && $SC advance jira__PROJ-200 --actor agent --unit billing; echo "rc=$?"   # exempt -> implement->verify rc=0
$SC advance jira__PROJ-200 --actor agent --unit billing; echo "rc=$?"   # empty catalog -> smoke exit 2 EMPTY -> refuse rc=1, stays verify
ls "$LIFECYCLE_STATE_DIR"/jira__PROJ-200.verify.log
```

Expected: unshipped/uncovered subtask refuses (rc=1, message about a shipped workflow lacking a smoke test); after
exempt, implement→verify rc=0; verify on empty catalog yields real smoke exit 2 and a `.verify.log` diagnostic, refuses
rc=1. No traceback.

- [ ] **Step 2: Record result**

```bash
echo "## A6 lifecycle advance + smoke gates: PASS (real smoke runtime)" >> "$SCRATCH/run-log.md"
```

### Task A7: ai-hooks JSON-validation refactor deep exercise (fail-open)

**Files:**

- Test (exercise): `.skillshare/skills/ai-hooks-integration/scripts/runtime/{unified_hook,tool_config,cli_wrapper}.py`

- [ ] **Step 1: unified_hook stdin validation (incl. the `[1,2,3]` crash check)**

```bash
cd .skillshare/skills/ai-hooks-integration/scripts
for p in '{"tool_name":"Bash","tool_input":{"command":"ls"}}' 'not json at all' '42' '"hello"' '' '   ' '[1,2,3]'; do
  printf '%s' "$p" | python3 runtime/unified_hook.py --source claude --no-detect; echo "exit=$? for: $p"
done
cd - >/dev/null
```

Expected: valid object → allow JSON, exit 0; garbage/primitive → stderr `Invalid input JSON...` then allow JSON, exit 0;
empty/whitespace → allow JSON exit 0; `[1,2,3]` → **per matrix this reproduces an AttributeError crash** — if it
tracebacks, record as a Phase A red (array payload not coerced). Confirm exit code regardless.

- [ ] **Step 2: tool_config.load_json + cli_wrapper run_hook**

Run the `tool_config.py load_json` and `cli_wrapper.py run_hook` blocks verbatim from the matrix (ai-hooks cluster),
writing fixtures into `$SCRATCH`.

Expected: `load_json` always returns a dict (good→`{'a':1}`, array/num/missing→`{}`, bad/empty/ws→`{}` + warning);
cli_wrapper deny→exit 1 (original not run), allow→runs, garbage/empty→warning then runs (fail-open exit 0).

- [ ] **Step 3: Record result, noting any `[1,2,3]` crash as a red**

```bash
echo "## A7 ai-hooks JSON refactor: <PASS|RED: unified_hook array crash>" >> "$SCRATCH/run-log.md"
```

### Task A8: `lint_on_edit_hook.sh` repo-path exercise

**Files:**

- Test (exercise): `configs/claude/scripts/lint_on_edit_hook.sh`, `tests/bats/lint_on_edit_hook.bats`

- [ ] **Step 1: Run the bad/good/mutation/fail-open exercise (matrix, verbatim)**

```bash
SCRIPT=configs/claude/scripts/lint_on_edit_hook.sh; TMP=$(mktemp -d)
payload(){ python3 -c "import json,sys;print(json.dumps({'tool_input':{'file_path':sys.argv[1]}}))" "$1"; }
f="$TMP/bad.sh"; printf '#!/usr/bin/env bash\ndir=$1\ncd $dir\n' > "$f"; printf '%s' "$(payload "$f")" | bash "$SCRIPT"; echo "exit=$?"   # SC2164/SC2086 on stderr, exit 0
g="$TMP/ok.sh"; printf '#!/usr/bin/env bash\nfoo=1\necho "$foo"\n' > "$g"; printf '%s' "$(payload "$g")" | bash "$SCRIPT" 2>&1; echo "exit=$?"   # no stderr, exit 0
before=$(shasum "$f"|awk '{print $1}'); printf '%s' "$(payload "$f")" | bash "$SCRIPT" >/dev/null 2>&1; after=$(shasum "$f"|awk '{print $1}'); [ "$before" = "$after" ] && echo UNCHANGED
rm -rf "$TMP"
```

Expected: every invocation exits 0; bad file emits a `lint-on-edit:` finding block on stderr; clean file silent; file
bytes UNCHANGED (advisory, no mutation).

- [ ] **Step 2: Run its bats suite**

```bash
bats tests/bats/lint_on_edit_hook.bats 2>&1 | tail -5; echo "rc=${PIPESTATUS[0]}"
```

Expected: 15 ok, rc=0.

- [ ] **Step 3: Record result**

```bash
echo "## A8 lint_on_edit_hook: PASS (advisory, no-mutation, fail-open)" >> "$SCRATCH/run-log.md"
```

### Task A9: bootstrap graphify toggle plumbing + semantic colors (read-only, NO deploy)

**Files:**

- Test (exercise): `bootstrap/lib/config.sh`, `bootstrap/lib/install.sh`, `bootstrap/lib/deploy.sh`,
  `configs/claude/scripts/check_status.sh`

- [ ] **Step 1: Toggle precedence (sourced functions, temp SERVICES_CONFIG)**

Run the three `write_services_config`/`load_existing_config`/`parse_bootstrap_args --enable-graphify` blocks verbatim
from the matrix (bootstrap cluster).

Expected: default emits `enabled: true` + `command: graphify`; file `enabled: false` honored when no flag;
`--enable-graphify` beats file=false; `./bootstrap.sh --help | grep -i graphify` lists the flags.

- [ ] **Step 2: Semantic colors + check_status graphify D4 (read-only against live, sandboxed services.yml for the
  counted-agent check)**

```bash
grep -nE 'disabled\)"' bootstrap/lib/deploy.sh   # all five (disabled) lines use YELLOW ○, not RED ✗
SBX=$(mktemp -d); mkdir -p "$SBX/.claude/config"
printf 'services:\n  claude:\n    enabled: true\n  gemini:\n    enabled: true\n  cursor:\n    enabled: false\n  codex:\n    enabled: false\n  antigravity:\n    enabled: false\n  graphify:\n    enabled: true\n' > "$SBX/.claude/config/services.yml"
HOME="$SBX" bash configs/claude/scripts/check_status.sh 2>&1 | grep -iE 'Enabled Services|Graphify'; rm -rf "$SBX"
```

Expected: deploy.sh `(disabled)` lines all `${YELLOW}○`; sandbox check_status shows `Enabled Services (2/5)` (graphify
NOT counted — the D4 invariant) and `Graphify CLI not installed`.

- [ ] **Step 3: Record result**

```bash
echo "## A9 bootstrap graphify plumbing + semantic colors + D4: PASS (no deploy)" >> "$SCRATCH/run-log.md"
```

### Task A10: Phase A inventory checkpoint

- [ ] **Step 1: Summarize Phase A in the run log**

```bash
echo "## PHASE A SUMMARY" >> "$SCRATCH/run-log.md"
grep -E '^## A[0-9]' "$SCRATCH/run-log.md" >> "$SCRATCH/run-log.md"
echo "Reds to fix in A.5: subagent_policy.bats (smoke-orchestrator) + <any others found>" >> "$SCRATCH/run-log.md"
```

Expected: a consolidated Phase A pass/red list. If any red beyond the known one exists, each gets an A.5 fix-forward
cycle before Phase B.

---

## PHASE A.5 — Fix-forward the reds (TDD, on-branch, no auto-merge)

### Task A5.1: Fix `smoke-orchestrator` missing `subagents` disposition

**Files:**

- Modify: `configs/claude/config/command_config.yml` (smoke-orchestrator block, after line 123 `validation_tier: 1`)
- Test: `tests/bats/subagent_policy.bats`

**Interfaces:**

- Consumes: the confirmed RED from Task A3.
- Produces: a green `subagent_policy.bats` (all 6 tests) and a green full bats suite.

> Disposition rationale: `smoke-orchestrator` drives one config-driven engine sequentially via `smoke_test.py` — it does
> not fan work out to native sub-agents. Sibling runner skills `pr-regression-smoke` and `verify` are classified
> `never`. Choosing `never` + a `subagent_rationale` satisfies T1 (coverage) and T4 (rationale), and the skill body has
> no `## Sub-agent dispatch` section so T6 (no-contradiction) is also satisfied. No SKILL.md edit needed.

- [ ] **Step 1: Confirm the failing test (red)**

```bash
bats tests/bats/subagent_policy.bats 2>&1 | sed -n '1,8p'
```

Expected: FAIL — `not ok 1 ...` with `- smoke-orchestrator: no \`subagents\` disposition in tool_policies`.

- [ ] **Step 2: Add the disposition to the smoke-orchestrator block**

Edit `configs/claude/config/command_config.yml`. Locate the smoke-orchestrator block (the `validation_tier: 1` line
ending it, currently line 123):

```yaml
  smoke-orchestrator:
    allowed:

      - Bash       # smoke_test.py append/run/list/prune; opt-in playwright install
      - Read
      - Write      # appends/updates committed smoke-catalog/<app>.yaml
      - Edit
      - Skill      # may hand a failing gate to systematic-debugging

    forbidden: []
    parallel_agents: never        # an authoring/gate tool, not a cross-verification fan-out
    validation_tier: 1            # executes CLI/shell steps + handles env-injected secrets
    subagents: never
    subagent_rationale: Single config-driven engine runs the tiered catalog sequentially via one smoke_test.py run; no independent fan-out units.
```

(The two new lines are `subagents:` and `subagent_rationale:`, inserted after `validation_tier: 1`, matching the 4-space
indent of the sibling `pr-regression-smoke`/`lifecycle` blocks.)

- [ ] **Step 3: Run the gate to verify green**

```bash
bats tests/bats/subagent_policy.bats 2>&1 | tail -8; echo "rc=${PIPESTATUS[0]}"
```

Expected: all 6 tests `ok`, rc=0 (`check 'coverage' OK (89 skills)`).

- [ ] **Step 4: yamllint the config and run the full bats suite (no regression)**

```bash
yamllint configs/claude/config/command_config.yml; echo "yaml-rc=$?"
bats tests/bats/ 2>&1 | tail -5; echo "bats-rc=${PIPESTATUS[0]}"
```

Expected: yaml rc=0; full bats suite green.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/config/command_config.yml
git commit -m "fix(367): classify smoke-orchestrator subagents disposition (never)

Feature 363's smoke-orchestrator skill landed after 367's subagent_policy
gate; the dynamic coverage check went red post-merge (smoke-orchestrator had
no subagents disposition). Classify as never (one sequential engine, no
fan-out), matching pr-regression-smoke/verify.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A5.2: Fix-forward cycle for any OTHER Phase A red (template — apply per red found)

**Files:** vary by red. **Test:** the suite/exercise that surfaced it.

> Apply this TDD cycle to each additional red from Task A10 (e.g. the `unified_hook.py [1,2,3]` AttributeError if it
> reproduced, or a pytest/shellcheck failure). One commit per red.

- [ ] **Step 1: Reproduce the failure and capture the exact error**

```bash
# Run the precise failing command from the run log; paste its output.
```

Expected: the red reproduces deterministically. If it does not reproduce, do not "fix" it — investigate (could be
environmental); record and move on.

- [ ] **Step 2: Write/adjust a failing test that pins the correct behavior**

Add a test (bats case or pytest) asserting the intended behavior. For the `unified_hook` array case: assert an array
payload coerces to `{}` and exits 0 with no traceback.

- [ ] **Step 3: Run the test to confirm it fails**

```bash
# Run the new test; expect FAIL with the captured error signature.
```

- [ ] **Step 4: Make the minimal fix; run the test to confirm green**

```bash
# Apply the smallest change; re-run the new test (expect PASS) and the suite it belongs to.
```

- [ ] **Step 5: Commit (one red per commit)**

```bash
git add <files>
git commit -m "fix(<feat>): <one-line description of the red and fix>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task A5.3: Phase A green gate (do-it-right barrier)

- [ ] **Step 1: Re-run the full automated suite; confirm all green BEFORE Phase B**

```bash
bats tests/bats/ >/dev/null 2>&1; echo "bats-rc=$?"
python3 -m pytest tests/python/ -q >/dev/null 2>&1; echo "pytest-rc=$?"
ruff check --no-fix . >/dev/null 2>&1; echo "ruff-rc=$?"
echo "## A5 fix-forward complete; suite green (bats/pytest/ruff rc above)" >> "$SCRATCH/run-log.md"
```

Expected: all `rc=0`. **Do not proceed to Phase B until this gate is green.**

---

## PHASE B — Backup (reversibility before overwrite)

### Task B1: Snapshot live `~/.claude` (+ symlink targets + `~/.manifest`) with a status manifest

**Files:**

- Create: `~/.claude.bak-<ts>.tar.gz`, `<scratchpad>/backup-manifest.txt`

**Interfaces:**

- Consumes: the pre-run existence map from Task 0 Step 2.
- Produces: a tarball + `backup-manifest.txt` (every enumerated path tagged `PRESENT`/`ABSENT`) + a documented restore
  command (consumed by Task C2's coverage diff and any fail-stop restore).

- [ ] **Step 1: Build the status manifest and tarball (PRESENT paths archived; ABSENT recorded)**

```bash
TS=$(git -C /Users/chrismandich/Documents/GitHub/Manifest/.claude/worktrees/test-end-2-end rev-parse --short HEAD)-$(python3 -c "import time;print(int(time.time()))")
MANIFEST="$SCRATCH/backup-manifest.txt"; : > "$MANIFEST"
PRESENT=()
for p in "$HOME/.claude" "$HOME/.cursor/rules" "$HOME/.gemini" "$HOME/.codex" "$HOME/.antigravity" "$HOME/.manifest"; do
  if [ -e "$p" ]; then echo "PRESENT $p" >> "$MANIFEST"; PRESENT+=("$p"); else echo "ABSENT $p" >> "$MANIFEST"; fi
done
tar -czf "$HOME/.claude.bak-$TS.tar.gz" -C / "${PRESENT[@]#/}"
ls -lh "$HOME/.claude.bak-$TS.tar.gz"; cat "$MANIFEST"
```

Expected: tarball created (non-trivial size); manifest lists each path as PRESENT/ABSENT
(likely `ABSENT $HOME/.manifest`).

- [ ] **Step 2: Write the documented restore command into the run log**

```bash
{
  echo "## B1 BACKUP — restore procedure"
  echo "Restore PRESENT paths:  tar -xzf $HOME/.claude.bak-$TS.tar.gz -C /"
  echo "Remove ABSENT paths (created during the run):"
  grep '^ABSENT ' "$MANIFEST" | awk '{print "  rm -rf "$2}'
} >> "$SCRATCH/run-log.md"
sed -n '/## B1 BACKUP/,$p' "$SCRATCH/run-log.md"
```

Expected: run log now contains an unconditional restore: extract for PRESENT, `rm -rf` for each ABSENT path.

- [ ] **Step 3: Verify the tarball is readable (integrity)**

```bash
tar -tzf "$HOME/.claude.bak-$TS.tar.gz" >/dev/null && echo "BACKUP OK"
```

Expected: `BACKUP OK` (archive lists without error).

---

## PHASE C — Deploy (full interactive bootstrap)

### Task C1: Run `./bootstrap.sh` and capture output

**Files:**

- Exercise: `bootstrap.sh`, `bootstrap/lib/*`

**Interfaces:**

- Consumes: green Phase A + the Phase B backup.
- Produces: a populated/updated live `~/.claude` and the set of paths bootstrap wrote (consumed by Task C2).

- [ ] **Step 1: Confirm rsync is present (the cp fallback is unreachable; deploy_configs aborts without rsync)**

```bash
command -v rsync >/dev/null && echo "rsync present" || echo "MISSING rsync — bootstrap will abort; install before deploying"
```

Expected: `rsync present`. If missing, STOP and report (do not deploy).

- [ ] **Step 2: Run bootstrap interactively (USER answers prompts)**

> "Full interactive" was chosen. Interactive prompts must be answered by the user. The executor should ask the user to
> run it in-session via the `!` prefix so output is captured, OR run it and relay prompts:

```bash
./bootstrap.sh 2>&1 | tee "$SCRATCH/bootstrap-output.txt"
```

Expected: bootstrap completes with a success summary; `(disabled)` services render yellow ○; skills deploy to
`~/.claude/skills`; configs rsync to `~/.claude`. **If any step errors: STOP, report, offer restore (Task B1 restore
command).**

- [ ] **Step 3: Record deployed SHA + result**

```bash
echo "## C1 bootstrap: deployed SHA $(git rev-parse --short HEAD); exit captured in bootstrap-output.txt" >> "$SCRATCH/run-log.md"
```

### Task C2: Post-deploy backup-coverage check

**Files:**

- Read: `<scratchpad>/backup-manifest.txt`, `<scratchpad>/bootstrap-output.txt`

- [ ] **Step 1: Diff paths bootstrap wrote against the backup manifest; flag any uncovered**

```bash
# Paths under HOME modified during the run (newer than the backup tarball):
find "$HOME/.claude" "$HOME/.cursor" "$HOME/.gemini" "$HOME/.codex" "$HOME/.antigravity" -newer "$HOME/.claude.bak-"*.tar.gz -type f 2>/dev/null \
  | sed -E "s#$HOME/(\.[^/]+).*#$HOME/\1#" | sort -u > "$SCRATCH/written-roots.txt"
echo "Written roots:"; cat "$SCRATCH/written-roots.txt"
echo "Backed-up roots:"; awk '$1=="PRESENT"||$1=="ABSENT"{print $2}' "$SCRATCH/backup-manifest.txt"
```

Expected: every written root is covered by a manifest entry. **Any written path NOT in the manifest → STOP, extend the
backup (or report) before Phase D.**

- [ ] **Step 2: Record result**

```bash
echo "## C2 backup-coverage: all written roots covered" >> "$SCRATCH/run-log.md"
```

---

## PHASE D — Re-validate the deployed environment (deploy-sensitive subset)

### Task D1: Deployed skills + Cursor rules present and well-formed

- [ ] **Step 1: Confirm the new/changed skills are deployed**

```bash
for s in smoke-orchestrator lifecycle graphify; do
  test -f "$HOME/.claude/skills/$s/SKILL.md" && echo "OK $s" || echo "MISSING $s"
done
ls "$HOME/.cursor/rules/graphify.mdc" "$HOME/.cursor/rules/lifecycle.mdc" 2>&1
```

Expected: `OK smoke-orchestrator`, `OK lifecycle`, `OK graphify`; both Cursor `.mdc` rules present.

- [ ] **Step 2: Confirm the smoke-orchestrator fix reached the deployed config**

```bash
python3 -c "import yaml; tp=yaml.safe_load(open('$HOME/.claude/config/command_config.yml'))['tool_policies']; print('smoke-orchestrator:', tp['smoke-orchestrator'].get('subagents'))"
```

Expected: `smoke-orchestrator: never` (the A5.1 fix is live).

- [ ] **Step 3: Record result**

```bash
echo "## D1 deployed skills + cursor rules + smoke-orchestrator disposition: PASS" >> "$SCRATCH/run-log.md"
```

### Task D2: lifecycle real-default `init` (then prune) + deployed smoke gate

> Deploy-sensitive: confirms default paths resolve to `~/.claude`/`~/.manifest` post-deploy.

- [ ] **Step 1: One real-default init; confirm `~/.manifest` tree perms; then prune ONLY the test track**

```bash
SC="$HOME/.claude/scripts/lifecycle.sh"
MANIFEST_EXISTED=$(grep -q '^PRESENT .*/.manifest$' "$SCRATCH/backup-manifest.txt" && echo yes || echo no)
"$SC" init PROJ-DEPLOYCHECK
STATEDIR="$HOME/.manifest/lifecycle/state"
stat -f '%Sp %N' "$HOME/.manifest" "$STATEDIR"/jira__PROJ-DEPLOYCHECK.json
# Prune scope: whole tree only if it did NOT exist pre-run; else just the test track
if [ "$MANIFEST_EXISTED" = no ]; then rm -rf "$HOME/.manifest"; echo "pruned whole ~/.manifest (was absent pre-run)"; else rm -f "$STATEDIR"/jira__PROJ-DEPLOYCHECK.json; echo "pruned only test track"; fi
```

Expected: init creates `~/.manifest/.../jira__PROJ-DEPLOYCHECK.json`; dir `0700`, file `0600`; prune removes exactly the
test-created state (whole tree iff absent pre-run, else just the track — never user state).

- [ ] **Step 2: Deployed smoke gate resolves default `smoke_test.py` + providers config**

```bash
"$HOME/.claude/scripts/smoke_test.py" list 2>&1 | head -3; echo "rc=$?"
test -f "$HOME/.claude/config/lifecycle_providers.yml" && echo "providers config deployed"
```

Expected: `smoke_test.py list` runs against the deployed engine (rc 0); providers config present at the default path.

- [ ] **Step 3: Record result**

```bash
echo "## D2 lifecycle real-default init+prune + deployed smoke gate: PASS" >> "$SCRATCH/run-log.md"
```

### Task D3: Deployed `lint_on_edit_hook.sh` fires via the deployed hook wiring

- [ ] **Step 1: Drive the deployed hook on a bad edit**

```bash
TMP=$(mktemp -d); f="$TMP/bad.sh"; printf '#!/usr/bin/env bash\ndir=$1\ncd $dir\n' > "$f"
payload=$(python3 -c "import json,sys;print(json.dumps({'tool_input':{'file_path':sys.argv[1]}}))" "$f")
printf '%s' "$payload" | bash "$HOME/.claude/scripts/lint_on_edit_hook.sh"; echo "exit=$?"
rm -rf "$TMP"
```

Expected: a `lint-on-edit:` finding (SC2164/SC2086) on stderr, exit 0, file unmodified (advisory, fail-open) — now
running from the deployed path.

- [ ] **Step 2: Record result**

```bash
echo "## D3 deployed lint_on_edit_hook: PASS" >> "$SCRATCH/run-log.md"
```

### Task D4: `parallel_agent.py` orchestration round-trip

- [ ] **Step 1: Single-agent round-trip via the deployed orchestrator**

```bash
~/.claude/scripts/parallel_agent.py --claude-only --timeout 600 "Reply with the single word: OK" 2>&1 | tail -20; echo "rc=${PIPESTATUS[0]}"
```

Expected: a completed Claude agent response (OAuth CLI fallback path), rc=0, no consensus-collapse `BLOCKED` from an
absent agent (per memory `parallel-agent-false-block`). If a model-pin probe is desired, set `MODEL_CHECK_PROBE=1`.

- [ ] **Step 2: Record result**

```bash
echo "## D4 parallel_agent round-trip: PASS" >> "$SCRATCH/run-log.md"
```

### Task D5: `check_status.sh` / health-check semantic colors + graphify D4 (deployed)

- [ ] **Step 1: Run deployed check_status against live services.yml**

```bash
bash "$HOME/.claude/scripts/check_status.sh" 2>&1 | grep -iE 'Enabled Services|Graphify|disabled|not installed' | cat -v | head -20
```

Expected: enabled-service count rendered; Graphify shown as a managed tool (installed/not-installed/disabled) and NOT
counted toward orchestration readiness (D4); disabled rows render yellow `○` (`^[[1;33m○`), not red ✗.

- [ ] **Step 2: Record result and close the Phase D summary**

```bash
{ echo "## D5 check_status semantic colors + graphify D4: PASS"; echo "## PHASE D SUMMARY: all deploy-sensitive exercises PASS"; } >> "$SCRATCH/run-log.md"
```

---

## PHASE D.5 — Reconciliation + reviewable PR (no auto-merge)

### Task E1: Open the fix-forward PR; record deployed SHA + reconciliation path

**Files:**

- Read: `<scratchpad>/run-log.md`

**Interfaces:**

- Consumes: the green branch (A5 commits) and the run-log evidence.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin worktree-test-end-2-end 2>&1 | tail -5
```

Expected: branch pushed; PR-create URL or ready state.

- [ ] **Step 2: Open the PR with an evidence + reconciliation body (do NOT merge)**

```bash
DEPLOYED_SHA=$(git rev-parse --short HEAD)
gh pr create --base main --head worktree-test-end-2-end \
  --title "fix: 24h change-set validation — smoke-orchestrator disposition + reds" \
  --body "$(cat <<EOF
Validates the 4643b72..0722b88 change set (test -> backup -> deploy -> re-validate).

## Fixes

- Classify smoke-orchestrator subagents disposition (never) — closed the post-merge subagent_policy.bats red.

$(grep -E '^## A5 ' "$SCRATCH/run-log.md" || true)

## Evidence
Phase A/B/C/D summaries in the run log; all deploy-sensitive exercises passed.

## Reconciliation (main <-> deployed)
Deployed SHA: $DEPLOYED_SHA (branch worktree-test-end-2-end; NOT yet on main).

- On merge: re-run ./bootstrap.sh from main so ~/.claude == main.
- If delayed: ~/.claude runs branch code until merge (drift window recorded).
- If abandoned: restore from ~/.claude.bak-*.tar.gz (see run log restore command).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opened against `main`, unmerged. **Stop here — the user decides the merge.**

- [ ] **Step 3: Final run-log entry**

```bash
echo "## E1 PR opened (unmerged) at deployed SHA $(git rev-parse --short HEAD)" >> "$SCRATCH/run-log.md"
```

---

## Self-Review (plan ↔ spec coverage)

- **Phase A (test-first)** → Tasks A1–A10. **A.5 fix-reds-before-deploy** → A5.1 (known), A5.2 (template), A5.3 (green
  gate). **Phase B backup w/ PRESENT/ABSENT manifest + restore** → B1. **Phase C full interactive bootstrap + coverage
  diff** → C1, C2. **Phase D deploy-sensitive subset** → D1–D5 (matches the spec's selection criterion; status/anchor
  correctly Phase-A-only). **Phase D.5 reconciliation + no-auto-merge PR** → E1.

- **Deploy-sensitive selection** honored: D2 (real-default init), D3 (deployed hook), D1/D5 (deployed skills/status).
  Path-independent features (decide/gate, ai-hooks, ruff, status/anchor) stay in Phase A — matching the spec's
  "intentionally skips" list.

- **`~/.manifest` reversibility:** Task 0 records existence; B1 manifests it; D2 prunes scoped to pre-run existence — no
  orphaned state, no user-data loss.

- **Fail-stop after overwrite:** stated in C1 Step 2 and the Global Constraints; restore command produced in B1.
- **No placeholders:** every step has concrete commands; the one known fix (A5.1) has exact YAML; A5.2 is an explicit
  TDD template for genuinely-unknown reds (inherent to fix-forward, not a placeholder).
