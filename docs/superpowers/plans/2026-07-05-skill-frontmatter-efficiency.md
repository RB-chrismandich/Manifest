# Skill Front-Matter Efficiency Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 88 skills' YAML front-matter efficient (fewest gate bytes / loaded tokens) without weakening any skill's triggering.

**Architecture:** Two levers. Lever A mechanically inline-normalizes the 39 block-scalar descriptions (parsed triggering tokens preserved by construction). Lever B trims the ~17 over-norm descriptions, each gated by a skill-creator trigger-eval (no regression vs baseline). Then ratchet the `context_budget.bats` cap and add a house-style note.

**Tech Stack:** Bash/awk, Python 3 (PyYAML for parse-validation), bats, skill-creator `run_eval.py` (`claude -p` trigger evals).

## Global Constraints

- Scope is **descriptions only** — never touch skill `name:`, skill bodies, or the naming taxonomy. **One approved exception** (surfaced during Task 6, user-approved): `plan-manage`'s body had 12 pre-existing stale `.claude/.plans/` / `labels.yml` paths prefixed to `~/.claude/…` (path-prefix only, no prose/logic), because touching its description dragged the whole file into the `check-stale-repo-paths` changed-file gate. Task 6 Step 3 excludes `plan-manage` body diffs accordingly.
- **Exclude externally-managed skills**: any skill listed under `skills:` with a `source:` in `.skillshare/config.yaml` (currently only `ai-hooks-integration`). Never edit those files.
- House style: inline single-line description; **double-quote** iff the text contains `: ` (colon-space) or begins with a YAML indicator (`- ? : [ ] { } # & * ! | > ' " % @ \``); escape embedded `"` as `\"`.
- Non-trimmable content (Lever B): security keywords, negative-space cross-references ("Analysis-only; use X instead"), the skill's name-match cue and primary "use when" phrase.
- Every task ends green on `bats tests/bats/context_budget.bats` and a YAML-parse check of all touched SKILL.md files.
- The `~290` figure is a soft norm, not a hard per-skill cap. The only hard gate is the total-bytes budget.
- Work in worktree `feat/skill-frontmatter-efficiency`. Commit messages end with the repo's Co-Authored-By + Claude-Session trailers.

---

## File Structure

| Path | Responsibility | Change |
|---|---|---|
| `.skillshare/skills/*/SKILL.md` | Per-skill front-matter (the edits) | Modify (excl. externally-managed) |
| `$SCRATCH/measure_frontmatter.sh` | Byte/style/parse audit used across tasks | Create (scratch only) |
| `$SCRATCH/parse_check.py` | PyYAML validity + `name`/`description` presence check | Create (scratch only) |
| `$SCRATCH/normalize_frontmatter.py` | One-off Lever A in-place inline transform | Create (scratch only) |
| `$SCRATCH/verify_preserved.py` | Old-vs-new parsed-description equality check | Create (scratch only) |
| `$SCRATCH/evalsets/<name>.json` | Per-skill trigger eval sets (Lever B) | Create (scratch only) |
| `$SCRATCH/eval-evidence.md` | Baseline-vs-candidate eval verdicts (pasted into commit) | Create (scratch only) |
| `configs/claude/scripts/generate_cursor_rules.sh` | Cursor `.mdc` generator — inline-quote unescape (Task 2b) | Modify |
| `tests/bats/generate_cursor_rules.bats` | Embedded-quote generator test (Task 2b) | Modify |
| `configs/claude/scripts/command_catalog.py` | COMMANDS.md generator `_strip_quotes` — inline-quote unescape (Task 2b) | Modify |
| `tests/python/command_help/test_command_catalog.py` | Embedded-quote round-trip test (Task 2b) | Modify |
| `configs/cursor/rules/*.mdc` | Regenerated cursor rules for trimmed skills (Lever B) | Modify (generated) |
| `docs/COMMANDS.md` | Regenerated command index for trimmed skills (Lever B) | Modify (generated) |
| `.skillshare/skills/plan-manage/SKILL.md` | Approved body path-prefix fix (Task 6, gate-forced) | Modify (body — the one exception) |
| `tests/bats/context_budget.bats:116-127` | Total front-matter byte cap | Modify (D1 ratchet) |
| `docs/SKILL-NAMING.md` | Naming + now front-matter house style | Modify (D2) |

`$SCRATCH` is the session scratchpad directory (defined in Task 1 Step 0). Every
scratch script and data file lives under it and is **never committed** — only the
resulting `.skillshare/skills/*.md`, `tests/`, and `docs/` diffs enter the repo.

---

## Task 1: Audit harness + baseline snapshot

**Files:**
- Create: `$SCRATCH/measure_frontmatter.sh`

**Interfaces:**
- Produces: `measure_frontmatter.sh` prints, per skill, `<bytes> <style:inline|literal|folded> <name>`, plus TOTAL bytes and the externally-managed exclusion list; a `--parse` mode that asserts every SKILL.md front-matter is valid YAML.

- [ ] **Step 0: Define `$SCRATCH` and confirm exclusion data exists (fail closed)**

```bash
export SCRATCH="/private/tmp/claude-501/-Users-chrismandich-Documents-GitHub-Manifest/<session>/scratchpad"
mkdir -p "$SCRATCH/evalsets"
# .skillshare/config.yaml is committed infra; if it is missing/unparseable we
# cannot determine externally-managed skills -> STOP (never risk editing them).
python3 -c "import yaml,sys; yaml.safe_load(open('.skillshare/config.yaml'))" \
  || { echo "FATAL: .skillshare/config.yaml missing/unparseable — aborting (fail closed)"; exit 1; }
```
Expected: `$SCRATCH` exists; the config parses. If it aborts, do not proceed with any task.

- [ ] **Step 1: Write the audit script**

```bash
cat > "$SCRATCH/measure_frontmatter.sh" <<'EOF'
#!/usr/bin/env bash
# Audit skill front-matter: bytes (bats method), scalar style, YAML validity.
set -euo pipefail
ROOT="${1:-.skillshare/skills}"
excluded() { # skills with a source: in .skillshare/config.yaml
  awk '/^skills:/{s=1} s&&/^ *- name:/{n=$3} s&&/source:/{print n}' .skillshare/config.yaml
}
EXCL="$(excluded)"
total=0
for f in "$ROOT"/*/SKILL.md; do
  name="$(basename "$(dirname "$f")")"
  case " $EXCL " in *" $name "*) tag="EXCLUDED";; *) tag="";; esac
  bytes=$(awk '/^---$/{c++; next} c==1' "$f" | wc -c | tr -d ' ')
  style=$(awk '/^description: *\|/{print "literal";f=1} /^description: *>/{print "folded";f=1} /^description: [^|>]/{print "inline";f=1} f{exit}' "$f")
  total=$((total + bytes))
  printf "%5d  %-7s %-9s %s\n" "$bytes" "$style" "$tag" "$name"
done
echo "TOTAL: $total"
EOF
chmod +x "$SCRATCH/measure_frontmatter.sh"
```

- [ ] **Step 2: Add `--parse` YAML-validity mode**

```bash
# Append to measure_frontmatter.sh: `measure_frontmatter.sh --parse`
# extracts front-matter and runs it through PyYAML; nonzero on any parse error.
```

```python
# $SCRATCH/parse_check.py — invoked by --parse
import sys, glob, yaml
bad = 0
for f in glob.glob(".skillshare/skills/*/SKILL.md"):
    fm = []
    with open(f) as fh:
        lines = fh.read().splitlines()
    assert lines[0] == "---"
    for ln in lines[1:]:
        if ln == "---": break
        fm.append(ln)
    try:
        d = yaml.safe_load("\n".join(fm))
        assert "name" in d and "description" in d, f"{f}: missing keys"
    except Exception as e:
        print(f"PARSE FAIL {f}: {e}"); bad += 1
sys.exit(1 if bad else 0)
```

- [ ] **Step 3: Run baseline and record it**

Run: `"$SCRATCH/measure_frontmatter.sh" | tee "$SCRATCH/baseline.txt"; python3 $SCRATCH/parse_check.py`
Expected: TOTAL ≈ 21656; parse check exits 0; `ai-hooks-integration` tagged EXCLUDED.

- [ ] **Step 4: No commit** (scratchpad only — nothing enters the repo this task).

---

## Task 2: Lever A — inline-normalize the 39 block-scalar descriptions

**Files:**
- Modify: each `.skillshare/skills/<name>/SKILL.md` whose style is `literal` or `folded` and is not EXCLUDED
- Create: `$SCRATCH/normalize_frontmatter.py` (not committed)

**Interfaces:**
- Consumes: baseline audit from Task 1.
- Produces: every non-excluded description on one inline line, quoted per the colon-space rule; parsed value equal to the old parsed value with newlines folded to single spaces.

- [ ] **Step 1: Write the transform (parse → re-emit inline)**

```python
# $SCRATCH/normalize_frontmatter.py
# Replaces ONLY the description span in place; every other front-matter line
# (name, any future keys) and the body are left byte-for-byte unchanged.
import glob, re, yaml
YAML_INDICATORS = set("-?:[]{}#&*!|>'\"%@`\\")  # includes backslash per spec
# Derive excluded set dynamically from skillshare provenance (spec constraint) —
# any skill with a `source:` is externally managed. No hardcoded name.
cfg = yaml.safe_load(open(".skillshare/config.yaml")) or {}
EXCL = {s["name"] for s in (cfg.get("skills") or []) if s.get("source")}
def needs_quote(v):
    return (": " in v) or (v[:1] in YAML_INDICATORS)
def emit(v):
    v = " ".join(v.split())           # fold whitespace/newlines to single spaces
    return '"' + v.replace('"', '\\"') + '"' if needs_quote(v) else v
for f in glob.glob(".skillshare/skills/*/SKILL.md"):
    name = f.split("/")[-2]
    if name in EXCL: continue
    text = open(f).read()
    lines = text.split("\n")
    assert lines[0] == "---", f"{f}: no front-matter"
    end = lines.index("---", 1)                       # closing marker index
    di = next(i for i in range(1, end) if re.match(r'^description:', lines[i]))
    if not re.match(r'^description:\s*[|>]', lines[di]):
        continue                                       # already inline — outside Lever A scope
    dj = di + 1                                        # end of the description span
    while dj < end and not re.match(r'^[A-Za-z0-9_-]+:', lines[dj]):
        dj += 1                                        # consume indented/blank block-scalar lines
    val = yaml.safe_load("\n".join(lines[di:dj]))["description"]
    new_lines = lines[:di] + [f"description: {emit(val)}"] + lines[dj:]
    out = "\n".join(new_lines)
    if out != text:                                   # skip already-inline & minimal
        open(f, "w").write(out)
        print("normalized", name)
```

This edits the `description` span only — `name:` and any other keys pass through untouched (satisfies the spec's "preserve all other metadata" rule even though today every skill has exactly `name` + `description`).

- [ ] **Step 2: Dry-run guard — confirm no genuine multi-line loss**

Run: `awk '/^description: *\|/{c=1;next} c&&/^[a-zA-Z_-]+:/{exit} c&&/^---/{exit} c{print}' .skillshare/skills/*/SKILL.md | grep -nE '^\s*$|^\s*[-*] ' || echo "SAFE: no blank lines / list markers in any literal block"`
Expected: `SAFE: …` (verified during design — 0 of 31 are genuine multi-line). If any line prints, STOP and hand that skill to Lever B manual review instead.

- [ ] **Step 3: Apply the transform**

Run: `python3 $SCRATCH/normalize_frontmatter.py`
Expected: ~39 "normalized <name>" lines (excludes any already-inline).

- [ ] **Step 4: Verify parsed values are semantically preserved**

```python
# $SCRATCH/verify_preserved.py — compare old (git HEAD) vs new parsed descriptions
import subprocess, glob, yaml
def parse(text):
    lines = text.splitlines(); end = lines.index("---", 1)
    return yaml.safe_load("\n".join(lines[1:end]))["description"]
fails = 0
for f in glob.glob(".skillshare/skills/*/SKILL.md"):
    old = subprocess.run(["git","show",f"HEAD:{f}"],capture_output=True,text=True).stdout
    if not old: continue
    o = " ".join(parse(old).split()); n = " ".join(parse(open(f).read()).split())
    if o != n:
        print(f"TOKEN DRIFT {f}:\n  old={o!r}\n  new={n!r}"); fails += 1
print("OK: all preserved" if not fails else f"{fails} drifted")
import sys; sys.exit(1 if fails else 0)
```

Run: `python3 $SCRATCH/verify_preserved.py`
Expected: `OK: all preserved` — whitespace-normalized parsed descriptions are identical (proves Lever A changed only formatting, not trigger tokens).

- [ ] **Step 5: Verify YAML validity, byte drop, and budget gate**

Run: `python3 $SCRATCH/parse_check.py && "$SCRATCH/measure_frontmatter.sh" | tail -1 && bats tests/bats/context_budget.bats`
Expected: parse exits 0; TOTAL dropped below 21656; all context_budget tests pass.

- [ ] **Step 6: Commit Lever A**

```bash
git add .skillshare/skills/
git commit -m "refactor(skills): inline-normalize block-scalar front-matter (Lever A)

Convert literal/folded description block scalars to inline single-line,
quoting the colon-space descriptions. Parsed triggering tokens preserved
(verified: whitespace-normalized values identical). Recovers block-wrapper
indentation bytes from always-loaded context.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JpWri5Fi9XhWyGZLuSL42R"
```

---

## Task 2b: Fix the derived-doc generators' inline-quote escaping (Lever A follow-up)

**Why:** Lever A inlined 5 descriptions containing embedded quotes
(`ai-code-audit`, `graphify`, `repo-clean`, `pr-monitor`, `pr-smoke`). **Two**
derived-doc generators — a shared bug class — string-strip the outer quotes on
their inline path but never YAML-unescape `\"`, then re-escape:
the bash `generate_cursor_rules.sh` (cursor `.mdc`) emits `\\\"` in frontmatter +
a backslashed body quote, and the Python `command_catalog.py:_strip_quotes`
(COMMANDS.md) leaks literal backslashes and pulls out-of-scope skills into the
diff. Block scalars (the pre-Lever-A form) were unaffected, so `origin/main`
shipped correct output; the branch does not. CI regenerates both (cursor-rules
clean-tree check + `generate_commands_doc.py --check`), so both must be fixed
before the PR. (Discovered during Task 6 regen; not in the original design.
Fixed as two commits: bd2738e bash, 094242b Python.)

**Files:**
- Modify: `configs/claude/scripts/generate_cursor_rules.sh` (bash inline-path unescape) + `tests/bats/generate_cursor_rules.bats`
- Modify: `configs/claude/scripts/command_catalog.py` (`_strip_quotes` inline-path unescape) + `tests/python/command_help/test_command_catalog.py`

**Constraint:** both per-skill paths stay dependency-light — the bash loop stays
pure-bash (no python), and `command_catalog.py` keeps its line-based frontmatter
reader (no `yaml.safe_load`, since descriptions legitimately contain `: `).
Unescape order: `\"`→`"` before `\\`→`\`.

**Acceptance:** `bats tests/bats/generate_cursor_rules.bats` + `pytest
tests/python/command_help/` pass (each with a new embedded-quote case); running
both generators leaves `git status --porcelain docs/COMMANDS.md
configs/cursor/rules/` empty (they reproduce the correct committed derived files
for all 88 skills); `generate_commands_doc.py --check` exit 0; `shellcheck`
clean. Two isolated fix commits — generators + tests only, no `.mdc`/`SKILL.md`.

---

## Task 3: Lever B — eval-guarded content trim of over-norm descriptions

**Files:**
- Modify: each non-excluded `.skillshare/skills/<name>/SKILL.md` with front-matter > 290 bytes (from Task 1 audit, re-measured post-Lever-A)
- Create: `$SCRATCH/evalsets/<name>.json`, `$SCRATCH/eval-evidence.md` (not committed; evidence pasted into commit body)

**Interfaces:**
- Consumes: `run_eval.py` at `~/.claude/plugins/cache/claude-plugins-official/skill-creator/*/skills/skill-creator/scripts/run_eval.py`, run as `python3 -m scripts.run_eval` from the skill-creator dir.
- **Detector patch (required):** upstream `run_eval.py`'s detector aborts on the first non-Skill `tool_use` (the model runs a locate-file Bash step first), zeroing all positives. Copy the scripts into `$SCRATCH/evalscripts/` and patch the detector to scan the full transcript for a `Skill`/`Read` `tool_use` naming the temp skill, then run that patched copy. Apply the SAME patch to baseline and candidate so the relative accept/reject gate is unaffected (absolute rates stay noisy → relative signals only). A non-zero baseline on every accepted skill confirms the patch is live. See the design's "Eval-harness caveat".
- Produces: trimmed descriptions with recorded baseline-vs-candidate trigger evidence.

- [ ] **Step 1: Compute the trim list (post-Lever-A)**

Metric: **total front-matter bytes** — the exact quantity `context_budget.bats`
counts and what the design's "18 over norm" figure measured. Skill names are 2–4
short ASCII tokens (~20–30 bytes), so front-matter bytes track description length
closely; the norm is a soft ~290-byte front-matter target, not a hard per-skill cap.

Run: `"$SCRATCH/measure_frontmatter.sh" | awk '$1>290 && $0 !~ /EXCLUDED/{print $NF}'`
(`$NF` = skill name; the `!~ /EXCLUDED/` guard drops externally-managed skills
regardless of field position.)
Expected: ~17 skills (e.g. pr-smoke, pr-monitor, deploy-diagnose-drift, ci-audit-triggers, speckit-audit-tasks, data-validate-live, ai-code-audit, spec-review, skill-evolve, deploy-reconcile, shell-audit-errexit, issue-prep-auto, ci-harden-workflow, branch-clean, deploy-retire-component, version-pin, pr-review).

- [ ] **Step 2: For each skill, generate an eval set with sibling negatives**

For skill `<name>` in domain `<D>` (first name token): create `$SCRATCH/evalsets/<name>.json` with skill-creator's schema — `should_trigger` queries (paraphrases of the skill's real use-cases) and `should_not_trigger` queries that **include** real use-cases of same-domain siblings (all other `<D>-*` skills) plus 2–3 unrelated tasks. Use the skill-creator analyzer agent to draft, then hand-check that every sibling is represented in the negatives.

Example (`pr-review`, domain `pr`): negatives include a `pr-address-comments` task ("fix the review comments on my PR"), a `pr-monitor` task ("babysit my open PR"), a `pr-smoke` task ("regression-test the repo after this PR"). If a trim makes `pr-review` fire on those, the eval catches the collision.

- [ ] **Step 3: Baseline eval (original description)**

```bash
# Define once for all eval steps in this task (same shell session):
PWD_REPO="$(git rev-parse --show-toplevel)"
SC="$HOME/.claude/plugins/cache/claude-plugins-official/skill-creator"
SCDIR="$(dirname "$(find "$SC" -name run_eval.py | head -1)")/.."
( cd "$SCDIR" && python3 -m scripts.run_eval \
    --skill-path "$PWD_REPO/.skillshare/skills/<name>" \
    --eval-set "$SCRATCH/evalsets/<name>.json" \
    --runs-per-query 3 --num-workers 6 --verbose ) | tee "$SCRATCH/base-<name>.json"
```
Expected: a baseline should-trigger rate and should-not-trigger (false-fire) rate. Record both.

- [ ] **Step 4: Draft the trim (preserve non-trimmable content)**

Rewrite the description shorter, keeping: name-match cue, primary "use when" phrase, all security keywords, and all negative-space cross-references. Target ≤ ~275 bytes front-matter. Keep it inline + colon-space-quoted per Global Constraints.

- [ ] **Step 5: Candidate eval (override, file untouched)**

```bash
( cd "$SCDIR" && python3 -m scripts.run_eval \
    --skill-path "$PWD_REPO/.skillshare/skills/<name>" \
    --eval-set "$SCRATCH/evalsets/<name>.json" \
    --description "<trimmed description>" \
    --runs-per-query 3 --num-workers 6 --verbose ) | tee "$SCRATCH/cand-<name>.json"
```

- [ ] **Step 6: Gate — accept only on no regression**

Accept the trim **iff** candidate should-trigger rate ≥ baseline **and** candidate false-fire rate ≤ baseline. Otherwise revise wording (Step 4) and re-run, or keep the original description unchanged. Append a one-line verdict per skill to `$SCRATCH/eval-evidence.md` (`<name>: trigger base→cand, false base→cand, VERDICT`).

- [ ] **Step 7: Apply accepted trims to the files**

Edit each accepted skill's `description:` in place. Skills that failed the gate keep their original wording (that is a valid, expected outcome — record it).

- [ ] **Step 8: Verify parse + budget after trims**

Run: `python3 $SCRATCH/parse_check.py && bats tests/bats/context_budget.bats`
Expected: parse exits 0; budget green (total now lower still).

- [ ] **Step 9: Commit Lever B with evidence**

```bash
git add .skillshare/skills/
git commit -m "refactor(skills): trim over-norm descriptions, eval-verified (Lever B)

Trim N descriptions toward the ~275-byte norm. Each trim gated by a
skill-creator trigger eval with sibling-derived negatives; accepted only
when should-trigger rate held and false-fire rate did not rise. Skills that
regressed kept their original wording. Evidence:
<paste eval-evidence.md table>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JpWri5Fi9XhWyGZLuSL42R"
```

---

## Task 4: D1 — ratchet the budget cap

**Files:**
- Modify: `tests/bats/context_budget.bats:116-127` (the `total > 22800` gate + comment block)

- [ ] **Step 1: Measure the final total**

Run: `"$SCRATCH/measure_frontmatter.sh" | tail -1`
Expected: prints the post-trim TOTAL (call it `T`).

- [ ] **Step 2: Set the new cap to `T + 800`**

Edit the two `22800` occurrences (the `-gt` comparison and the echoed budget) to `T + 800` (rounded up to the next 50). Append a comment line to the block matching the file's existing convention, e.g.:

```
# Lowered 22800 -> <NEW> (2026-07-05): set-wide front-matter efficiency pass
# (inline-normalize + eval-guarded trims) cut the total to <T>; new cap leaves
# ~800 bytes (~3 skills) headroom. See
# docs/superpowers/specs/2026-07-05-skill-frontmatter-efficiency-design.md.
```

- [ ] **Step 3: Verify the gate still passes at the new cap**

Run: `bats tests/bats/context_budget.bats`
Expected: all tests pass (total ≤ new cap, with ~800 headroom).

- [ ] **Step 4: Sanity-check the cap actually bites**

Run: `grep -nE '22800|-gt' tests/bats/context_budget.bats`
Expected: no stray `22800` remains in the skill-frontmatter test; the new value is present in both the comparison and the echo.

- [ ] **Step 5: Commit**

```bash
git add tests/bats/context_budget.bats
git commit -m "test(budget): ratchet skill front-matter cap after efficiency pass (D1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JpWri5Fi9XhWyGZLuSL42R"
```

---

## Task 5: D2 — front-matter house-style note

**Files:**
- Modify: `docs/SKILL-NAMING.md` (add a "Front-Matter Style" section after "The Pattern")

- [ ] **Step 1: Add the section**

```markdown
## Front-Matter Style

The `description:` is always-loaded triggering text (injected every session) and
is byte-counted by `tests/bats/context_budget.bats`. Keep it efficient:

- **Inline single-line.** No `|` (literal) or `>` (folded) block scalars — their
  indentation is pure byte overhead in always-loaded context.
- **Quote when needed.** Double-quote the value if it contains `: ` (colon-space)
  or begins with a YAML indicator (`- ? : [ ] { } # & * ! | > ' " % @ \``); escape
  embedded `"` as `\"`.
- **~290-char soft norm.** Not a hard cap (the only hard gate is the total-bytes
  budget), but stay near it. If a genuinely-new skill pushes the total over the
  cap, do a set-wide trim before raising the budget.
- **Never trim away** security keywords, negative-space cross-references
  ("Analysis-only; use `X` instead"), the name-match cue, or the primary
  "use when" phrase — these are what make the skill trigger correctly and
  keep siblings from firing.
```

- [ ] **Step 2: Lint the doc**

Run: `npx markdownlint-cli --config .markdownlint.jsonc docs/SKILL-NAMING.md`
Expected: no errors (MD013 line_length 120 — keep lines wrapped ≤120).

- [ ] **Step 3: Commit**

```bash
git add docs/SKILL-NAMING.md
git commit -m "docs(skills): document front-matter efficiency house style (D2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JpWri5Fi9XhWyGZLuSL42R"
```

---

## Task 6: Full regression + PR

**Files:** none (verification + PR)

- [ ] **Step 1: Run the real pre-commit over the diff**

Run: `pre-commit run --from-ref origin/main --to-ref HEAD --all-files 2>&1 | tail -30` (or `pre-commit run --files $(git diff --name-only origin/main)`)
Expected: markdownlint, yamllint, and all hooks pass. Fix any hygiene the diff drags in before proceeding.

- [ ] **Step 2: Run the affected bats gates**

Run: `bats tests/bats/context_budget.bats tests/bats/skill_naming.bats`
Expected: all pass (naming untouched → green; budget at new cap → green).

- [ ] **Step 3: Confirm no skill body or name changed** (scope: SKILL.md only, except the one approved plan-manage path fix)

Run: `git diff origin/main --name-only -- '.skillshare/skills/*/SKILL.md' | grep -v '/plan-manage/' | xargs -I{} git diff origin/main -- {} | grep -E '^\+' | grep -vE '^\+\+\+|^\+(name: |description: )' || echo "OK: only description lines changed in skill files"`
Expected: `OK: …` — within SKILL.md files (excluding `plan-manage`) the only added lines are `description:` (name + bodies untouched). `plan-manage`'s body path-prefix fix is the single approved exception (see Global Constraints). Derived files (COMMANDS.md, `configs/cursor/rules/*.mdc`), the generator fixes (`generate_cursor_rules.sh` + `command_catalog.py` + their tests), and `context_budget.bats` legitimately change and are covered by Steps 3b/2b.

- [ ] **Step 3b: Confirm derived docs are in sync (the two CI gates)**

Regeneration happens at commit time (Task 2b + Lever B commit). Verify here that nothing is stale:
```bash
configs/claude/scripts/generate_commands_doc.py --check   # COMMANDS.md gate (ci.yml)
configs/claude/scripts/generate_cursor_rules.sh           # cursor-rules gate (ci.yml)
git status --porcelain docs/COMMANDS.md configs/cursor/rules/
```
Expected: `--check` exits 0; `git status` is empty. Any dirty file = a stale derived doc that must be regenerated and folded into its source commit before the PR.

- [ ] **Step 4: Confirm every externally-managed skill is untouched**

Run:
```bash
EXCL=$(awk '/^skills:/{s=1} s&&/^ *- name:/{n=$3} s&&/source:/{print n}' .skillshare/config.yaml)
rc=0
for n in $EXCL; do
  d=$(git diff origin/main -- ".skillshare/skills/$n/" | wc -l | tr -d ' ')
  [ "$d" = 0 ] || { echo "MODIFIED externally-managed skill: $n ($d diff lines)"; rc=1; }
done
[ "$rc" = 0 ] && echo "OK: all externally-managed skills untouched"
```
Expected: `OK: all externally-managed skills untouched` (dynamically covers every `source:` skill, not just `ai-hooks-integration`).

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/skill-frontmatter-efficiency
gh pr create --title "refactor(skills): set-wide front-matter efficiency pass" --body "$(cat <<'BODY'
Inline-normalizes block-scalar skill descriptions (Lever A, mechanical) and
trims over-norm descriptions with skill-creator trigger evals guarding against
regressions and cross-skill collisions (Lever B). Ratchets the
context_budget.bats cap (D1) and documents the house style (D2).

- Total front-matter: 21656 → <T> bytes; cap 22800 → <T+800>.
- Trigger tokens preserved on Lever A (verified parsed-value identical mod whitespace).
- Lever B trims accepted only on no eval regression; evidence in commit bodies.
- ai-hooks-integration (externally managed) untouched.

Spec: docs/superpowers/specs/2026-07-05-skill-frontmatter-efficiency-design.md
Plan: docs/superpowers/plans/2026-07-05-skill-frontmatter-efficiency.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

---

## Self-Review (author checklist — completed)

- **Spec coverage:** Lever A → Task 2; Lever B + eval + sibling negatives → Task 3; provenance exclusion → Tasks 1–2 + Task 6 Step 4; colon-space quoting → Global Constraints + Task 2 Step 1; D1 → Task 4; D2 → Task 5; CI-safety → Task 6. All design sections map to a task.
- **Placeholder scan:** `<name>`, `<T>`, `<D>`, `<trimmed description>` are per-iteration substitutions with defined derivation, not unfilled TODOs. No "add error handling"/"write tests for the above".
- **Type/name consistency:** `measure_frontmatter.sh`, `parse_check.py`, `normalize_frontmatter.py`, `verify_preserved.py` referenced consistently across tasks; eval field names (should_trigger/should_not_trigger, `--description`, `--eval-set`, `--skill-path`) match `run_eval.py`'s verified interface.
- **Known judgement points (intended, not gaps):** the exact trim wording per skill and the eval-set query drafting are LLM-authored at execution time under the stated acceptance gate — the plan fixes the *gate*, not the prose.
