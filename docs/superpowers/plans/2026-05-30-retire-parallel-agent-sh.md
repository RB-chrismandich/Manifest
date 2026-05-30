# Retire `parallel_agent.sh` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the deprecated `configs/claude/scripts/parallel_agent.sh` and repoint every live/instructional reference to the maintained `parallel_agent.py` (direct invocation), leaving dated historical records factually intact.

**Architecture:** Order matters to avoid mangling: (1) remove the two `.sh`-specific syntax-validation steps (CI + pre-commit), (2) `git rm` the script and its bats suite, (3) bulk `perl -pi` repoint `.sh`→`.py` across the remaining live files (explicit excludes for historical + hand-edit files), (4) hand-edit the prose that must not be blind-swapped (`install.sh`, the `.py` docstring), (5) verify.

**Tech Stack:** Bash, Python (`parallel_agent.py`), `perl` (portable in-place edit), `bats`, `pytest`, `shellcheck`, `markdownlint-cli2`.

**Spec:** `docs/superpowers/specs/2026-05-30-retire-parallel-agent-sh-design.md`

---

## Reference classes (from spec)

- **Repoint (live/instructional):** 17 skill `SKILL.md`s, `bootstrap.sh`,
  `bootstrap/lib/deploy.sh`, `configs/claude/config/{command_config,services}.yml`,
  `configs/claude/scripts/check_status.sh`, `configs/claude/settings.local.json`,
  `configs/cursor/rules/orchestration.mdc`, `configs/gemini/GEMINI.md`,
  `CLAUDE.md`, `AGENTS.md`, `README.md`, `configs/claude/CLAUDE.md`,
  `configs/claude/references/{layout,orchestration,parallel-agent}.md`,
  `docs/*.md` (COMMANDS, CONFIGURATION, GETTING_STARTED, TROUBLESHOOTING,
  ARCHITECTURE_DIAGRAMS, PRE_COMMIT, README), `docs/templates/**`,
  `tests/test_helper/README.md`.
- **Hand-edit (not blind-swap):** `.github/workflows/ci.yml` (remove step),
  `.pre-commit-config.yaml` (remove hook), `bootstrap/lib/install.sh` (delete the
  "Bash version" line), `configs/claude/scripts/parallel_agent.py` (docstring).
- **Delete:** `configs/claude/scripts/parallel_agent.sh`, `tests/bats/parallel_agent.bats`.
- **DO NOT touch (historical):** `.Jules/sentinel.md`, `docs/SHELL_ANALYSIS_REPORT.md`,
  `docs/VALIDATION_REPORT.md`, `docs/superpowers/**`.

---

## Task 1: Remove the `.sh`-specific syntax-validation steps

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Remove the CI step**

In `.github/workflows/ci.yml`, delete the step (in the `validate` job):
```yaml
      - name: Validate parallel_agent.sh syntax
        run: bash -n configs/claude/scripts/parallel_agent.sh
```
(The generic `bash -n configs/claude/scripts/*.sh` loop and the skill/script
counts remain and adjust automatically.)

- [ ] **Step 2: Remove the pre-commit hook**

In `.pre-commit-config.yaml`, delete this hook block (under `- repo: local`):
```yaml
      # Validate parallel_agent.sh syntax
      - id: validate-parallel-agent
        name: Validate parallel_agent.sh syntax
        entry: bash -n
        language: system
        files: ^configs/claude/scripts/parallel_agent\.sh$
```
Leave the sibling `Validate bootstrap.sh syntax` hook intact.

- [ ] **Step 3: Verify both files still parse**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.pre-commit-config.yaml')); print('both valid')"
grep -n "parallel_agent" .github/workflows/ci.yml .pre-commit-config.yaml || echo "no parallel_agent refs remain in CI/pre-commit"
```
Expected: `both valid`; the only remaining hit (if any) is the `ci.yml` pip-deps
comment mentioning `parallel_agent.py` — that is correct and stays.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml .pre-commit-config.yaml
git commit -m "ci: drop parallel_agent.sh syntax-validation step and pre-commit hook (#256)"
```

---

## Task 2: Delete the deprecated script and its bats suite

**Files:**
- Delete: `configs/claude/scripts/parallel_agent.sh`
- Delete: `tests/bats/parallel_agent.bats`

- [ ] **Step 1: Confirm pytest covers `.py` before removing bats**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
python3 -m pytest tests/python/ -q 2>&1 | tail -1
```
Expected: `54 passed` (the `.py` retains coverage; the bats suite only tested the
`.sh` CLI). If this is not green, STOP and report.

- [ ] **Step 2: Remove the files**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git rm configs/claude/scripts/parallel_agent.sh tests/bats/parallel_agent.bats
```

- [ ] **Step 3: Verify removal and that bats still discovers the rest**

```bash
test ! -e configs/claude/scripts/parallel_agent.sh && echo "script gone"
test ! -e tests/bats/parallel_agent.bats && echo "bats gone"
./node_modules/.bin/bats tests/bats/ 2>&1 | grep -E "^not ok" || echo "BATS: no failures"
```
Expected: `script gone`, `bats gone`, `BATS: no failures` (install runner first
if needed: `npm install --no-save bats markdownlint-cli2`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove deprecated parallel_agent.sh and its bats suite (#256)"
```

---

## Task 3: Bulk-repoint live/instructional references

**Files:** all live files containing `parallel_agent.sh`, EXCLUDING historical
records and the hand-edit files (Task 4).

- [ ] **Step 1: Build the exclude-filtered file list and repoint with perl**

Run (one command — computes the set, excludes historical + hand-edit + deleted,
then replaces in place):
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
grep -rlZ 'parallel_agent\.sh' . \
  | tr '\0' '\n' \
  | grep -v '/\.git/' \
  | grep -vE '\.Jules/sentinel\.md|docs/SHELL_ANALYSIS_REPORT\.md|docs/VALIDATION_REPORT\.md|docs/superpowers/' \
  | grep -vE '\.github/workflows/ci\.yml|\.pre-commit-config\.yaml|bootstrap/lib/install\.sh|configs/claude/scripts/parallel_agent\.py' \
  | while IFS= read -r f; do
      perl -pi -e 's{parallel_agent\.sh}{parallel_agent.py}g' "$f"
      echo "repointed: $f"
    done
```
Expected: a list of repointed files (skills, docs, configs, JSON, references,
`bootstrap.sh`, `deploy.sh`, `check_status.sh`, `command_config.yml`, etc.).

- [ ] **Step 2: Spot-check representative swaps**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
grep -n "parallel_agent.py" configs/claude/config/command_config.yml | grep script_path   # script_path now .py
grep -n "parallel_agent.py" configs/claude/settings.local.json                            # permission entry now .py
grep -n "parallel_agent.py" bootstrap/lib/deploy.sh | head -3                              # alias/examples/required-file now .py
```
Expected: `script_path: ~/.claude/scripts/parallel_agent.py`; the
`Bash(~/.claude/scripts/parallel_agent.py:*)` permission; deploy.sh alias +
required-file now `.py`.

- [ ] **Step 3: Confirm no historical file was touched**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git diff --name-only | grep -E '\.Jules/sentinel\.md|SHELL_ANALYSIS_REPORT|VALIDATION_REPORT|docs/superpowers/' && echo "ERROR: historical file modified" || echo "historical records untouched (good)"
```
Expected: `historical records untouched (good)`.

- [ ] **Step 4: Validate edited machine-readable files still parse**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
python3 -c "import yaml; [yaml.safe_load(open(f)) for f in ['configs/claude/config/command_config.yml','configs/claude/config/services.yml']]; print('yml ok')"
python3 -c "import json; [json.load(open(f)) for f in ['configs/claude/settings.local.json','docs/templates/settings-low-risk.json','docs/templates/permissions/django-web-app.json','docs/templates/permissions/express-api.json','docs/templates/permissions/go-microservices.json','docs/templates/permissions/python-monorepo.json']]; print('json ok')"
```
Expected: `yml ok` and `json ok`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: repoint live references parallel_agent.sh -> .py (#256)"
```

---

## Task 4: Hand-edit the prose that must not be blind-swapped

**Files:**
- Modify: `bootstrap/lib/install.sh`
- Modify: `configs/claude/scripts/parallel_agent.py`

- [ ] **Step 1: Fix the install.sh messaging**

In `bootstrap/lib/install.sh`, the `else` branch (~lines 186-190) currently reads:
```bash
        print_warning "Python not found"
        print_info "The new Python parallel agent (parallel_agent.py) requires Python 3.9+"
        print_info "The Bash version (parallel_agent.sh) will still work without Python"
        print_info ""
```
Delete the now-false "Bash version" line and drop the stale "new" wording:
```bash
        print_warning "Python not found"
        print_info "The parallel agent (parallel_agent.py) requires Python 3.9+"
        print_info ""
```

- [ ] **Step 2: Fix the parallel_agent.py docstring**

In `configs/claude/scripts/parallel_agent.py`, line ~5 currently references the
now-deleted script:
```python
This is a Python rewrite of parallel_agent.sh with improved async handling,
```
Change it to not dangle a reference to a deleted file:
```python
This is the parallel agent orchestrator with async handling,
```

- [ ] **Step 3: Verify**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
grep -n "Bash version" bootstrap/lib/install.sh || echo "install.sh: stale line removed"
grep -n "parallel_agent.sh" configs/claude/scripts/parallel_agent.py || echo "py docstring: no .sh reference"
bash -n bootstrap/lib/install.sh && echo "install.sh parses"
python3 -c "import ast; ast.parse(open('configs/claude/scripts/parallel_agent.py').read()); print('py parses')"
```
Expected: all four OK lines.

- [ ] **Step 4: Commit**

```bash
git add bootstrap/lib/install.sh configs/claude/scripts/parallel_agent.py
git commit -m "docs: drop stale parallel_agent.sh prose from install.sh and py docstring (#256)"
```

---

## Task 5: Full verification

**Files:** none (verification only)

- [ ] **Step 1: No live `.sh` references remain (historical-only)**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
echo "=== remaining parallel_agent.sh hits (should be ONLY historical) ==="
grep -rn "parallel_agent\.sh" . 2>/dev/null | grep -v '/\.git/'
echo "=== loose/typo sweep ==="
grep -rniE "parallel.agent\.sh" . 2>/dev/null | grep -v '/\.git/' | grep -viE '\.Jules/sentinel|SHELL_ANALYSIS|VALIDATION_REPORT|docs/superpowers' || echo "no live/typo hits"
```
Expected: every remaining hit is in `.Jules/sentinel.md`,
`docs/SHELL_ANALYSIS_REPORT.md`, `docs/VALIDATION_REPORT.md`, or
`docs/superpowers/**`. Zero in live/instructional files.

- [ ] **Step 2: Test suites + lint green**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
./node_modules/.bin/bats tests/bats/ 2>&1 | grep -E "^not ok" || echo "BATS: no failures"
python3 -m pytest tests/python/ -q 2>&1 | tail -1
shellcheck -S warning configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh && echo "shellcheck clean"
./node_modules/.bin/markdownlint-cli2 "AGENTS.md" "CLAUDE.md" "README.md" "docs/*.md" 2>&1 | tail -1
```
Expected: `BATS: no failures`, `54 passed`, `shellcheck clean`,
`Summary: 0 error(s)`.

- [ ] **Step 3: Sandbox bootstrap — deploy + verify_installation + examples show `.py`**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
SBX=$(mktemp -d /tmp/retire_e2e.XXXXXX)
printf 'y\n' | HOME="$SBX" ./bootstrap.sh --skip-install --skip-auth --force --disable-cursor --disable-gemini --disable-codex > "$SBX/out.log" 2>&1
echo "bootstrap exit: $?"
grep -q "parallel_agent.py" "$SBX/out.log" && echo "alias/examples reference .py" || echo "(no .py in summary output)"
grep -i "parallel_agent.sh" "$SBX/out.log" && echo "WARN: .sh still printed" || echo "no .sh in output"
test -f "$SBX/.claude/scripts/parallel_agent.py" && echo "py deployed" || echo "FAIL py deploy"
test ! -e "$SBX/.claude/scripts/parallel_agent.sh" && echo "sh not deployed (good)"
rm -rf "$SBX"
```
Expected: exit 0; alias/examples reference `.py`; no `.sh` in output; `.py`
deployed; `.sh` absent. (`verify_installation` must pass — its required-file list
now checks `.py`.)

- [ ] **Step 4: Clean tree**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git status -s; echo "(empty = clean)"
git log --oneline main..HEAD
```
Expected: clean tree; Task 1-4 commits present.

---

## Notes for the implementer

- **Order is load-bearing:** Tasks 1-2 (remove CI/pre-commit steps, delete files)
  run BEFORE Task 3's bulk `perl` so those landmine files are never blind-swapped.
- **Do NOT touch historical records** (`.Jules/sentinel.md`,
  `docs/SHELL_ANALYSIS_REPORT.md`, `docs/VALIDATION_REPORT.md`,
  `docs/superpowers/**`) — the bulk command excludes them; Task 3 Step 3 asserts it.
- **`shellcheck -S warning` stays** — do not revert to strict (spec decision).
- The `command_config.yml` `script_path:` (live) and the permission JSON entries
  (`Bash(...:*)`) are real consumers — confirm they became `.py` (Task 3 Step 2).
