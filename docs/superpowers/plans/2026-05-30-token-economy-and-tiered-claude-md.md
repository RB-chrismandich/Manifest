# Token Economy Skill + Tiered CLAUDE.md Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `/token-economy` session-mutator skill and split the 685-line always-loaded `configs/claude/CLAUDE.md` into a lean core + on-demand `references/`, cutting both dynamic-session and fixed-per-turn token cost without degrading accuracy.

**Architecture:** Deliverable A is a self-contained skill in the library (zero baseline cost, opt-in). Deliverable B moves ~450 lines of reference tables/prose out of the always-loaded core into four `references/*.md` files that bootstrap already deploys via `rsync -a`, leaving a ~180–220 line core that points to them with action-verb triggers.

**Tech Stack:** Markdown (skills + CLAUDE.md), YAML (`command_config.yml`), bash (`bootstrap.sh`/`deploy.sh`), `skillshare`, `markdownlint-cli2`, `bats`.

**Spec:** `docs/superpowers/specs/2026-05-30-token-economy-and-tiered-claude-md-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `.skillshare/skills/token-economy/SKILL.md` | The session-mutator skill | **Create** |
| `configs/claude/config/command_config.yml` | Tool policy registry | **Modify** (add `token-economy`) |
| `configs/claude/references/parallel-agent.md` | parallel_agent.sh flags/models/schema/env/output | **Create** (moved) |
| `configs/claude/references/orchestration.md` | cross-verification, workflow integration, error handling, orchestrated review | **Create** (moved) |
| `configs/claude/references/git-platform.md` | platform detection + git_ops | **Create** (moved) |
| `configs/claude/references/layout.md` | config-files table + ~/.claude file tree | **Create** (moved) |
| `configs/claude/CLAUDE.md` | Lean always-on core + Reference Index | **Modify** (trim 685→~200) |

**Section → destination map (from spec; current line numbers in `configs/claude/CLAUDE.md`):**

| Current section (lines) | Destination |
|-------------------------|-------------|
| Title + intro (1–5) | **core** |
| Quick Usage (6–55) | **core**, trimmed to single-line examples (multi-line/commented variants → `references/parallel-agent.md`) |
| Options (56–80), Model Selection (81–100), Credit Exhaustion Fallback (101–112), JSON Output Schema (113–154), Environment Variables (155–168) | `references/parallel-agent.md` |
| Proactive Decision Framework (169–210) | **core** |
| Cross-Verification Patterns (211–243) | `references/orchestration.md` |
| Validation Criteria (244–265) | **core** |
| Workflow Integration (266–292), Error Handling (293–304) | `references/orchestration.md` |
| Output Location (305–318) | `references/parallel-agent.md` |
| Orchestrated Code Review Workflow + phases + example (319–452) | `references/orchestration.md` |
| Skills (Available/Command Usage/Auto-Triggered) (453–517) | **core** |
| Git Platform Detection & Operations (518–603) | `references/git-platform.md` |
| Configuration Files (604–615), File Structure (616–663) | `references/layout.md` |
| Plan Management (664–685) | **core** |

---

## Task 1: Create the `token-economy` skill

**Files:**
- Create: `.skillshare/skills/token-economy/SKILL.md`

- [ ] **Step 1: Create the skill directory and file**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
mkdir -p .skillshare/skills/token-economy
```

- [ ] **Step 2: Write `SKILL.md` with the exact content below**

Create `.skillshare/skills/token-economy/SKILL.md`:
```markdown
---
name: token-economy
description: |
  Switch the current session into terse, surgical, clarify-first mode to cut
  token usage. Invoke when responses are verbose, during long refactors, or to
  conserve budget. Opt-in session mutator — re-invoke if it wears off.
---

# Token Economy Mode

Adopt the following for the REST of this session, starting now. These override
default verbosity and apply until the session ends or the user says otherwise.

## Output

- No filler: skip "Sure", "Here's the…", and closing summaries. Lead with the result.
- Do not re-explain code you just wrote unless asked (an explicit "Explain:" prompt).
- Match response length to the task — a one-line answer for a one-line question.

## Edits (surgical, by capability)

- Do NOT emit text-based diffs or full-file rewrites when a programmatic
  file-editing tool is available — use it (targeted edits).
- If text output is your only option, emit the minimum line-replacement snippet
  required; never reprint a whole file for a small change.

## Before coding

- If an implementation detail is genuinely ambiguous, ask ONE targeted question
  first. Do not guess and generate throwaway code.

## Context (balanced, NOT starved)

- Read what the change actually depends on — types, signatures, callers. Avoid
  speculative whole-tree crawls and re-reading unchanged files.
- A wrong edit caused by under-reading costs far more than one extra dependency
  read. Conserve tokens; do not starve context.

## Persistence caveat

This mode lives only in the session context. In a long session the invocation
can scroll out of the active window and default verbosity returns — if you
notice that (roughly 30k+ tokens in), re-invoke `/token-economy`. True always-on
enforcement would require a hook (e.g. `ai-hooks-integration`); that is out of
scope for this skill.
```

- [ ] **Step 3: Verify frontmatter parses and required fields exist**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
python3 -c "
import re, sys
t = open('.skillshare/skills/token-economy/SKILL.md').read()
m = re.match(r'^---\n(.*?)\n---\n', t, re.S)
assert m, 'no frontmatter'
import yaml
fm = yaml.safe_load(m.group(1))
assert fm.get('name') == 'token-economy', fm
assert fm.get('description'), 'missing description'
print('frontmatter OK:', fm['name'])
"
```
Expected: `frontmatter OK: token-economy`

- [ ] **Step 4: Verify markdownlint passes on the new skill**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
./node_modules/.bin/markdownlint-cli2 ".skillshare/skills/token-economy/SKILL.md" 2>&1 | tail -3
```
Expected: `Summary: 0 error(s)` (install bats/markdownlint first if missing: `npm install --no-save markdownlint-cli2`).

- [ ] **Step 5: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add .skillshare/skills/token-economy/SKILL.md
git commit -m "feat: add token-economy session-mutator skill"
```

---

## Task 2: Register the skill in `command_config.yml`

**Files:**
- Modify: `configs/claude/config/command_config.yml` (under `tool_policies:`)

- [ ] **Step 1: Add the tool policy entry**

In `configs/claude/config/command_config.yml`, under `tool_policies:` (after the
last existing entry), add:
```yaml
  token-economy:
    allowed:
      - Read
      - Glob
      - Grep
    forbidden:
      - Bash
      - Write
    parallel_agents: never
    validation_tier: 2
```

- [ ] **Step 2: Verify YAML still parses**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
python3 -c "import yaml; d=yaml.safe_load(open('configs/claude/config/command_config.yml')); assert 'token-economy' in d['tool_policies']; print('token-economy registered')"
```
Expected: `token-economy registered`

- [ ] **Step 3: Verify yamllint (relaxed, as CI runs it)**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
yamllint -d relaxed configs/claude/config/command_config.yml; echo "exit=$?"
```
Expected: `exit=0` (line-length warnings are allowed under relaxed).

- [ ] **Step 4: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add configs/claude/config/command_config.yml
git commit -m "feat: register token-economy in tool_policies"
```

---

## Task 3: Extract `references/parallel-agent.md`

**Files:**
- Create: `configs/claude/references/parallel-agent.md`

- [ ] **Step 1: Create the references directory**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
mkdir -p configs/claude/references
```

- [ ] **Step 2: Build the file from the moved sections**

Read `configs/claude/CLAUDE.md`. Create `configs/claude/references/parallel-agent.md`
beginning with this H1, then the named sections **verbatim** (promote their
`###` headings to `##` so heading levels increment from the H1 without a gap):
```markdown
# Parallel Agent Reference

> Full flags, model tiers, credit fallback, JSON schema, env vars, and output
> location for `~/.claude/scripts/parallel_agent.sh`. Referenced from CLAUDE.md.
```
Then append, in this order, the bodies of these current `CLAUDE.md` sections,
each as a `##` heading:
- Options (current lines 56–80)
- Model Selection (81–100)
- Credit Exhaustion Fallback (101–112)
- JSON Output Schema (113–154)
- Environment Variables (155–168)
- Output Location (305–318)

- [ ] **Step 3: Verify heading hygiene + markdownlint**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
head -1 configs/claude/references/parallel-agent.md | grep -qE '^# ' && echo "H1 OK"
./node_modules/.bin/markdownlint-cli2 "configs/claude/references/parallel-agent.md" 2>&1 | tail -2
```
Expected: `H1 OK` and `Summary: 0 error(s)`.

- [ ] **Step 4: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add configs/claude/references/parallel-agent.md
git commit -m "docs: extract parallel-agent reference from CLAUDE.md"
```

---

## Task 4: Extract `references/orchestration.md`

**Files:**
- Create: `configs/claude/references/orchestration.md`

- [ ] **Step 1: Build the file from the moved sections**

Create `configs/claude/references/orchestration.md` starting with this H1, then
the named section bodies verbatim (promote `###`→`##`, keep their existing
`###`/`####` children one level below):
```markdown
# Orchestration Reference

> Multi-agent review workflow, cross-verification patterns, synthesis, and
> validation phases. Referenced from CLAUDE.md.
```
Append, in order, these current `CLAUDE.md` sections:
- Cross-Verification Patterns (211–243)
- Workflow Integration (266–292)
- Error Handling (293–304)
- Orchestrated Code Review Workflow + all phases + Example Orchestration Flow (319–452)

- [ ] **Step 2: Verify heading hygiene + markdownlint**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
head -1 configs/claude/references/orchestration.md | grep -qE '^# ' && echo "H1 OK"
./node_modules/.bin/markdownlint-cli2 "configs/claude/references/orchestration.md" 2>&1 | tail -2
```
Expected: `H1 OK` and `Summary: 0 error(s)`.

- [ ] **Step 3: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add configs/claude/references/orchestration.md
git commit -m "docs: extract orchestration reference from CLAUDE.md"
```

---

## Task 5: Extract `references/git-platform.md`

**Files:**
- Create: `configs/claude/references/git-platform.md`

- [ ] **Step 1: Build the file**

Create `configs/claude/references/git-platform.md` starting with this H1, then
the "Git Platform Detection & Operations" section (current lines 518–603)
verbatim, with its `###` children promoted so levels increment from the H1:
```markdown
# Git Platform Reference

> Platform detection (`git_platform.sh`) and platform-agnostic operations
> (`git_ops.sh`) for GitHub/GitLab/plain git. Referenced from CLAUDE.md.
```

- [ ] **Step 2: Verify heading hygiene + markdownlint**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
head -1 configs/claude/references/git-platform.md | grep -qE '^# ' && echo "H1 OK"
./node_modules/.bin/markdownlint-cli2 "configs/claude/references/git-platform.md" 2>&1 | tail -2
```
Expected: `H1 OK` and `Summary: 0 error(s)`.

- [ ] **Step 3: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add configs/claude/references/git-platform.md
git commit -m "docs: extract git-platform reference from CLAUDE.md"
```

---

## Task 6: Extract `references/layout.md`

**Files:**
- Create: `configs/claude/references/layout.md`

- [ ] **Step 1: Build the file**

Create `configs/claude/references/layout.md` starting with this H1, then the
"Configuration Files" (604–615) and "File Structure" (616–663) sections
verbatim (promote `###`→`##` where needed):
```markdown
# Layout Reference

> Configuration-file map and the `~/.claude/` file tree. Referenced from CLAUDE.md.
```

- [ ] **Step 2: Verify heading hygiene + markdownlint**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
head -1 configs/claude/references/layout.md | grep -qE '^# ' && echo "H1 OK"
./node_modules/.bin/markdownlint-cli2 "configs/claude/references/layout.md" 2>&1 | tail -2
```
Expected: `H1 OK` and `Summary: 0 error(s)`.

- [ ] **Step 3: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add configs/claude/references/layout.md
git commit -m "docs: extract layout reference from CLAUDE.md"
```

---

## Task 7: Trim `CLAUDE.md` to core + add Reference Index

**Files:**
- Modify: `configs/claude/CLAUDE.md`

- [ ] **Step 1: Reconstruct the core by KEEPING only the core sections**

Rewrite `configs/claude/CLAUDE.md` so it contains, in order, ONLY:
1. Title + intro (current 1–5)
2. `## Parallel Agent Script` → `### Quick Usage` — **trimmed**: keep the 4
   single-line invocation examples only; drop multi-line/commented variants
   (those now live in `references/parallel-agent.md`)
3. The new **Reference Index** (Step 2 below), placed right after Quick Usage
4. `## Proactive Decision Framework` (169–210) verbatim
5. `## Validation Criteria` (244–265) verbatim
6. `## Skills` (453–517) verbatim
7. `## Plan Management` (664–685) verbatim

Everything else was moved in Tasks 3–6 and must NOT remain here.

- [ ] **Step 2: Insert the Reference Index (after Quick Usage)**

```markdown
## Reference Index

Read on demand (NOT auto-loaded). You MUST read the reference before related tasks:

- `~/.claude/references/parallel-agent.md` — Read for flag specs, JSON schema validation, or resolving Credit Exhaustion.
- `~/.claude/references/orchestration.md` — Read when running multi-agent validation or debugging cross-verification failures.
- `~/.claude/references/git-platform.md` — Read when automating PRs, branch detection, or git_ops failures.
- `~/.claude/references/layout.md` — Read when modifying config trees or mapping file locations.
```

- [ ] **Step 3: Verify line count is in range and no moved section remains**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
lines=$(wc -l < configs/claude/CLAUDE.md); echo "core lines: $lines"
[ "$lines" -ge 120 ] && [ "$lines" -le 260 ] && echo "LINE BUDGET OK" || echo "OUT OF RANGE (target ~180-220)"
echo "--- moved headings must be ABSENT from core ---"
for h in "### Options" "### Model Selection" "### JSON Output Schema" "### Environment Variables" \
         "## Cross-Verification Patterns" "## Workflow Integration" "## Error Handling" \
         "## Orchestrated Code Review Workflow" "## Output Location" \
         "## Git Platform Detection" "## File Structure"; do
  if grep -qF "$h" configs/claude/CLAUDE.md; then echo "LEAK: '$h' still in core"; fi
done
echo "(no LEAK lines above = clean)"
```
Expected: line count in range, "LINE BUDGET OK", no LEAK lines.

- [ ] **Step 4: Verify every reference file is pointed to (no orphans) + markdownlint**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
for f in parallel-agent orchestration git-platform layout; do
  grep -qF "references/$f.md" configs/claude/CLAUDE.md && echo "indexed: $f" || echo "ORPHAN: $f not in Reference Index"
done
./node_modules/.bin/markdownlint-cli2 "configs/claude/CLAUDE.md" 2>&1 | tail -2
```
Expected: all four `indexed:`, no `ORPHAN`, `Summary: 0 error(s)`.

- [ ] **Step 5: Commit**

```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git add configs/claude/CLAUDE.md
git commit -m "refactor: tier CLAUDE.md into lean core + references index"
```

---

## Task 8: Full verification (deploy + sync + tests)

**Files:** none (verification only)

- [ ] **Step 1: Sandbox bootstrap deploys core + references**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
SBX=$(mktemp -d /tmp/te_e2e.XXXXXX)
HOME="$SBX" ./bootstrap.sh --skip-install --skip-auth --force --disable-cursor --disable-gemini --disable-codex > "$SBX/out.log" 2>&1
echo "exit: $?"
test -f "$SBX/.claude/CLAUDE.md" && echo "core deployed" || echo "FAIL core"
ls "$SBX/.claude/references/"*.md 2>/dev/null && echo "references deployed" || echo "FAIL references"
test -d "$SBX/.claude/skills/token-economy" && echo "skill deployed" || echo "FAIL skill"
rm -rf "$SBX"
```
Expected: exit 0, "core deployed", four reference `.md` listed + "references deployed", "skill deployed".

- [ ] **Step 2: Skill syncs to Copilot target**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
skillshare sync 2>&1 | tail -2
test -d .github/skills/token-economy && echo "synced to copilot" || echo "FAIL sync"
```
Expected: "synced to copilot" (`.github/skills` is gitignored, so no tree dirt).

- [ ] **Step 3: Existing test suites + lint still green**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
./node_modules/.bin/bats tests/bats/ 2>&1 | grep -E "^not ok" || echo "BATS: no failures"
python3 -m pytest tests/python/ -q 2>&1 | tail -1
shellcheck -S warning bootstrap.sh bootstrap/lib/*.sh configs/claude/scripts/*.sh && echo "shellcheck clean"
```
Expected: "BATS: no failures", pytest "54 passed", "shellcheck clean".

- [ ] **Step 4: Confirm clean tree**

Run:
```bash
cd /Users/chrismandich/Documents/GitHub/Manifest
git status -s; echo "(empty = clean)"
git log --oneline -8
```
Expected: clean tree; Task 1–7 commits present.

---

## Notes for the implementer

- **Move, don't paraphrase.** Reference files get the section bodies **verbatim**
  (same tables, code blocks, prose) — only the heading levels shift (promote the
  top section heading to fit under the new H1) and content relocates.
- **Heading hygiene (markdownlint MD001):** every reference file starts with a
  single H1; the first moved section becomes `##`; its children stay one level
  deeper. No jump from `#` straight to `###`.
- **Line numbers drift** as you edit — the per-section line ranges are from the
  ORIGINAL 685-line file; use the section **headings** as the reliable anchors.
- **`references/` deploys for free:** `deploy.sh:76` uses `rsync -a` (recursive,
  creates dest subdirs); no bootstrap code change needed — Task 8 verifies it.
- Reference files are under `configs/claude/` and are NOT in CI's markdownlint
  glob (`AGENTS.md CLAUDE.md README.md docs/*.md`), but lint them anyway (Steps
  in Tasks 3–6) so the pre-commit hook and future globs stay green.
