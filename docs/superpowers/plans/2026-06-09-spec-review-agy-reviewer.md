# spec-review → agy Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the `/spec-review` engine's reviewer from `gemini` to `agy` (the Antigravity CLI), via a clean rename of the injectable seam — keeping the skill, save hook, debounce, detach, lock, and fail-open untouched.

**Architecture:** Pure reviewer swap inside the existing, deployed spec-review system. Rename the seam `SPEC_REVIEW_GEMINI` → `SPEC_REVIEW_CLI` (default `gemini` → `agy`) and `run_gemini` → `run_reviewer` in `spec_review.sh`; update the bats suite's stub + injections in lock-step (the tests invoke these names directly, so script + tests must change together to stay green); update the four doc references. `agy -p` was verified to read stdin and print headless exactly like `gemini -p`, so the invocation body is unchanged.

**Tech Stack:** Bash (3.2-safe), bats (bats-support/bats-assert), Markdown.

---

## File Structure

**Modify:**
- `configs/claude/scripts/spec_review.sh` — rename seam + function (6 references)
- `tests/bats/spec_review.bats` — rename stub/injections/test name (16 references) + 1 new "default reviewer is agy" test
- `.skillshare/skills/spec-review/SKILL.md` — Gemini → Antigravity/`agy` (4 spots)
- `docs/COMMANDS.md`, `CLAUDE.md`, `configs/claude/CLAUDE.md` — `/spec-review` row: "Gemini" → "Antigravity (`agy`)"

No new runtime files or engine components (this design + plan doc aside). No
behavior change beyond which CLI is invoked.

---

## Task 1: Coordinated reviewer rename (script + tests), default → agy

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh`
- Modify: `tests/bats/spec_review.bats`

This is one atomic task: the bats suite calls `run_gemini` and injects `SPEC_REVIEW_GEMINI`, so renaming only the script would red the suite. Script + tests change together.

- [ ] **Step 1: Edit `configs/claude/scripts/spec_review.sh` — the 6 references**

Apply these exact replacements:

Line ~10:
```bash
SPEC_REVIEW_CLI="${SPEC_REVIEW_CLI:-agy}"
```
(was `SPEC_REVIEW_GEMINI="${SPEC_REVIEW_GEMINI:-gemini}"`)

Lines ~102-107 (comment + function + body):
```bash
# run_reviewer PROMPT -> raw reviewer output. stdin carries the prompt body; the -p
# instruction is short. Errors propagate (caller decides fail-open vs surface).
run_reviewer() {
    local prompt="$1"
    printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" -p "Cross-reference the artifacts above per the instructions; output only the specified blocks or NO_ISSUES."
}
```
(was `run_gemini` / `$SPEC_REVIEW_GEMINI`)

Line ~177 (in `review()`):
```bash
    raw="$(run_reviewer "$prompt")"
```

Line ~189 (in `_silent_review_inline()`):
```bash
    if ! raw="$(run_reviewer "$prompt" 2>>"$state/error.log")"; then
```

Verify none remain:
```bash
grep -nE 'SPEC_REVIEW_GEMINI|run_gemini' configs/claude/scripts/spec_review.sh
```
Expected: no output.

- [ ] **Step 2: Rename identifiers in `tests/bats/spec_review.bats`**

Run (BSD/macOS sed):
```bash
sed -i '' \
  -e 's/SPEC_REVIEW_GEMINI/SPEC_REVIEW_CLI/g' \
  -e 's/run_gemini/run_reviewer/g' \
  -e 's/_fake_gemini/_fake_reviewer/g' \
  -e 's#\$SANDBOX/gemini#$SANDBOX/agy#g' \
  tests/bats/spec_review.bats
```
This renames the seam injections, the function calls, the stub helper, and the stub's file path (`$SANDBOX/gemini` → `$SANDBOX/agy`).

- [ ] **Step 3: Fix the residual `gemini` mentions the sed didn't catch (comment + stub heredoc)**

The `_fake_reviewer` helper still has a comment and an internal stub naming "gemini". Replace the helper definition so it's clean. Open `tests/bats/spec_review.bats`, find the `_fake_reviewer()` helper (near line 83) and ensure it reads exactly:

```bash
_fake_reviewer() {  # writes a stub reviewer CLI named 'agy' into SANDBOX
    cat > "$SANDBOX/agy" <<'STUB'
#!/usr/bin/env bash
cat >/dev/null   # consume stdin
printf '⚠️  CLARIFICATION REQUIRED: Migration\n   ├─ Location: plan vs tasks\n   ├─ The Gap: zero-downtime vs destructive\n   ├─ Recommended Direction: split into 3 tasks\n   └─ Reason Why: locking violates the constraint\n'
STUB
    chmod +x "$SANDBOX/agy"
}
```

Confirm no `gemini` remains:
```bash
grep -niE 'gemini' tests/bats/spec_review.bats
```
Expected: no output.

- [ ] **Step 4: Run the suite — confirm it stays green**

Run: `bats tests/bats/spec_review.bats`
Expected: all existing tests PASS (27), zero failures. (The rename is behavior-preserving; the stub just has a new name.)

Run: `shellcheck configs/claude/scripts/spec_review.sh`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): rename reviewer seam to SPEC_REVIEW_CLI, default to agy"
```

---

## Task 2: Assert the default reviewer is `agy`

**Files:**
- Modify: `tests/bats/spec_review.bats`

- [ ] **Step 1: Append the failing test**

Add to `tests/bats/spec_review.bats`:

```bash
@test "default reviewer is agy when SPEC_REVIEW_CLI is unset" {
    # Put a stub named 'agy' on PATH; do NOT set SPEC_REVIEW_CLI.
    _fake_reviewer                      # creates $SANDBOX/agy
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    PATH="$SANDBOX:$PATH" \
        SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" "$SANDBOX"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}
```

- [ ] **Step 2: Run it — confirm it passes**

Run: `bats tests/bats/spec_review.bats -f "default reviewer is agy"`
Expected: PASS (the script's default `SPEC_REVIEW_CLI` is now `agy`, which resolves to the stub on PATH). If it FAILS with the stub not found, the default isn't `agy` — fix Task 1 Step 1.

- [ ] **Step 3: Run the full file**

Run: `bats tests/bats/spec_review.bats`
Expected: 28 tests pass, zero failures.

- [ ] **Step 4: Commit**

```bash
git add tests/bats/spec_review.bats
git commit -m "test(spec-review): assert default reviewer is agy"
```

---

## Task 3: Update docs (skill + command tables)

**Files:**
- Modify: `.skillshare/skills/spec-review/SKILL.md`
- Modify: `docs/COMMANDS.md`
- Modify: `CLAUDE.md`
- Modify: `configs/claude/CLAUDE.md`

- [ ] **Step 1: `.skillshare/skills/spec-review/SKILL.md` — 4 replacements**

- Line ~5: `consistency using an independent model (Gemini), and surface structured` → `consistency using an independent model (Antigravity / `agy`), and surface structured`
- Line ~12 heading: `# Spec Review (Gemini cross-reference)` → `# Spec Review (Antigravity cross-reference)`
- Line ~15: `artifacts. A second model (Gemini) reviews what Claude authored — catching` → `artifacts. A second model (Antigravity / `agy`) reviews what Claude authored — catching`
- Line ~32: `` `✓ No inconsistencies found.` Requires the `gemini` CLI (logged in). This skill is `` → `` `✓ No inconsistencies found.` Requires the `agy` CLI (logged in). This skill is ``

Confirm: `grep -niE 'gemini' .skillshare/skills/spec-review/SKILL.md` → no output.

- [ ] **Step 2: The three `/spec-review` command-table rows**

In each of `docs/COMMANDS.md`, `CLAUDE.md`, `configs/claude/CLAUDE.md`, replace `Independent Gemini cross-reference` with `Independent Antigravity (agy) cross-reference` in the `/spec-review` row.

Exact edit (same string in all three):
- Find: `| `/spec-review` | Independent Gemini cross-reference of spec/plan/tasks`
- Replace `Independent Gemini cross-reference` → `Independent Antigravity (agy) cross-reference`

- [ ] **Step 3: Verify no stray Gemini refs remain in spec-review surfaces**

Run:
```bash
grep -rniE 'gemini' .skillshare/skills/spec-review/ docs/COMMANDS.md \
  | grep -i 'spec-review\|spec_review\|cross-referenc' || echo "clean"
grep -niE 'spec-review.*gemini|gemini.*spec-review' CLAUDE.md configs/claude/CLAUDE.md || echo "tables clean"
```
Expected: `clean` / `tables clean`.

- [ ] **Step 4: Markdownlint the CI-gated docs**

Run: `npx --yes markdownlint-cli2 "CLAUDE.md" "docs/COMMANDS.md"`
Expected: 0 errors. (`configs/claude/CLAUDE.md` and the skill SKILL.md are not in the CI glob set — `AGENTS.md CLAUDE.md README.md docs/*.md` — but keep their edits clean anyway.)

- [ ] **Step 5: Commit**

```bash
git add .skillshare/skills/spec-review/SKILL.md docs/COMMANDS.md CLAUDE.md configs/claude/CLAUDE.md
git commit -m "docs(spec-review): reviewer is now Antigravity (agy), not Gemini"
```

---

## Task 4: Full verification + real-`agy` headless smoke

**Files:** none (verification only)

- [ ] **Step 1: Grep guard — zero `gemini` / old-seam references anywhere in the spec-review surface**

Run:
```bash
grep -rnE 'SPEC_REVIEW_GEMINI|run_gemini|_fake_gemini' \
  configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats && echo "FOUND (bad)" || echo "no old identifiers ✓"
```
Expected: `no old identifiers ✓`.

- [ ] **Step 2: Full suite + lint**

Run:
```bash
bats tests/bats/spec_review.bats          # 28 pass
bats tests/bats/                          # no regressions
shellcheck configs/claude/scripts/spec_review.sh
```
Expected: all green; shellcheck clean.

- [ ] **Step 3: Real-`agy` headless smoke (verification item #1 from the spec)**

Confirm the actual `agy` CLI works through the engine in non-interactive mode without hanging on a tool-permission prompt (the review is pure text analysis). Bounded so a hang can't stall:

```bash
export PATH="$HOME/.local/bin:$PATH"
mkdir -p /tmp/agysmoke/specs/001
printf '# Spec\nUse a zero-downtime migration.\n' > /tmp/agysmoke/specs/001/spec.md
printf '# Plan\nRun a destructive migration that locks tables.\n' > /tmp/agysmoke/specs/001/plan.md
( SPEC_REVIEW_TEMPLATE="$PWD/configs/claude/prompts/spec_review.md" \
    timeout_guard=300 bash configs/claude/scripts/spec_review.sh /tmp/agysmoke ) &
PID=$!; ( sleep 300; kill -9 $PID 2>/dev/null ) & W=$!
wait $PID; ec=$?; kill $W 2>/dev/null
echo "exit=$ec"
rm -rf /tmp/agysmoke
```
Expected: exit 0, and either structured `CLARIFICATION REQUIRED` findings (it should catch the zero-downtime vs destructive contradiction) or `✓ No inconsistencies found.` — and it must RETURN (no hang). If it hangs, note it: the detached silent path is unaffected (fail-open), but on-demand would need an explicit `--print-timeout`; capture that as a follow-up rather than blocking.

- [ ] **Step 4: Commit (if any verification tweak was needed; otherwise skip)**

```bash
git add -A && git commit -m "chore(spec-review): verify agy reviewer end-to-end" || echo "nothing to commit"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage:**
- Rename seam `SPEC_REVIEW_GEMINI` → `SPEC_REVIEW_CLI` (default agy) + `run_gemini` → `run_reviewer` → Task 1. ✓
- bats stub/injection rename in lock-step → Task 1. ✓
- "default reviewer is agy" test → Task 2. ✓
- Docs (SKILL.md + 3 tables) → Task 3. ✓
- Enforcement unchanged (hook/skill) — nothing to do; noted. ✓
- Verification item #1 (headless no-hang) → Task 4 Step 3. ✓
- Verification item #2 (5m timeout fine) — covered by the bounded smoke; no code change. ✓
- grep guard / no lingering gemini → Tasks 1–4. ✓

**Placeholder scan:** none — every edit shows exact before/after strings or exact sed/grep commands.

**Type/name consistency:** the new names `SPEC_REVIEW_CLI`, `run_reviewer`, `_fake_reviewer`, and stub file `agy` are used identically across Tasks 1, 2, 4.

**Note for executor:** `sed -i ''` is BSD/macOS syntax (this repo runs on macOS). On GNU/Linux use `sed -i` (no `''`). After Task 1's sed, re-read the `_fake_reviewer` helper to confirm Step 3's explicit form took (the sed renames identifiers/paths but Step 3 ensures the comment + stub filename are clean).
