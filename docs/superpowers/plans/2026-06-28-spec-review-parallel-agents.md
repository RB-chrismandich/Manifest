# Spec-Review via Parallel-Agent Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `spec-review` cross-reference planning artifacts with the parallel-agent panel (excluding the author, Claude) and synthesize one deduped findings list, replacing the single `agy` reviewer.

**Architecture:** `spec_review.sh` keeps assemble → review → format (on-demand + detached hook). A new `run_panel` becomes the default engine: it pipes the assembled prompt to `parallel_agent.py --json --no-claude --no-synthesize`, parses each successful agent's output, and — for ≥2 agents — merges them with a deterministic synthesizer pass via the existing single-CLI seam. `run_reviewer` (the `SPEC_REVIEW_CLI` seam) is retained as synthesizer + 0-agent fallback. Analysis-only; never edits artifacts.

**Tech Stack:** Bash (3.2-safe), python3 (json/yaml, already a dependency), bats + bats-support/bats-assert for tests, `parallel_agent.py` (existing orchestrator).

## Global Constraints

- Shell: `set -euo pipefail`; bash 3.2-safe (no `RETURN` trap, no associative arrays). — `spec_review.sh:8`
- Error output routed through `err() { echo "spec-review: $*" >&2; }` (project script convention). Exempt: usage/help, status/info lines.
- `--help` path must work before any dependency lookup (≤15 lines, exit 0).
- Fail-open contract (issue #317): in `--silent` hook mode, any reviewer/synth/write failure → write nothing, do NOT record the content hash, retry next save. Never block.
- Output contract unchanged: findings as `⚠️  CLARIFICATION REQUIRED:` blocks, or the single token `NO_ISSUES`.
- All new behavior must be reachable through injectable seams so bats can stub external CLIs (no real network calls in tests).
- New config defaults (add to the config block at top of `spec_review.sh`, verbatim):
  - `SPEC_REVIEW_PANEL_CMD="${SPEC_REVIEW_PANEL_CMD:-${SCRIPT_DIR}/parallel_agent.py}"`
  - `SPEC_REVIEW_SYNTH_CLI="${SPEC_REVIEW_SYNTH_CLI:-$SPEC_REVIEW_CLI}"`
  - `SPEC_REVIEW_MERGE_TEMPLATE="${SPEC_REVIEW_MERGE_TEMPLATE:-${SCRIPT_DIR}/../prompts/spec_review_merge.md}"`
  - `SPEC_REVIEW_TIMEOUT="${SPEC_REVIEW_TIMEOUT:-600}"`

---

## File Structure

- `configs/claude/scripts/spec_review.sh` — add config defaults, `assemble_merge_prompt`, `parse_panel_json`, `run_synthesizer`, `run_panel`; rewire `review()` + `_silent_review_inline()` to call `run_panel`; update status line. (existing seams `run_reviewer`, `assemble_prompt`, `format_findings`, hook funcs unchanged)
- `configs/claude/prompts/spec_review_merge.md` — NEW: synthesizer/merge instruction, same output contract.
- `tests/bats/spec_review.bats` — add tests for the four new functions + rewired entry points; keep all existing tests green.
- `.skillshare/skills/spec-review/SKILL.md` — description + body reflect the panel.
- `configs/gemini/GEMINI.md`, `configs/cursor/rules/spec-review.mdc` — engine-description references.

All test patterns follow the existing harness: `source "$SCRIPT"`, call functions directly, stub CLIs as executable files in `$SANDBOX`.

---

### Task 1: Merge template + config defaults + `assemble_merge_prompt`

**Files:**
- Create: `configs/claude/prompts/spec_review_merge.md`
- Modify: `configs/claude/scripts/spec_review.sh` (config block ~L11-16; new function after `assemble_prompt` ~L103)
- Test: `tests/bats/spec_review.bats`

**Interfaces:**
- Produces: `assemble_merge_prompt TEMPLATE REVIEWS_TEXT` → full merge prompt on stdout (template with `{{REVIEWS}}` replaced by `REVIEWS_TEXT`). New config vars `SPEC_REVIEW_PANEL_CMD`, `SPEC_REVIEW_SYNTH_CLI`, `SPEC_REVIEW_MERGE_TEMPLATE`, `SPEC_REVIEW_TIMEOUT`.

- [ ] **Step 1: Create the merge template**

Create `configs/claude/prompts/spec_review_merge.md`:

```markdown
<!-- configs/claude/prompts/spec_review_merge.md -->
# Merge Reviewer Findings

Several independent reviewers each cross-referenced a project's planning artifacts
for internal consistency. Their raw findings are below. Merge them into ONE list:

- Combine findings that describe the same gap into a single block (keep the
  clearest wording and the most concrete recommendation).
- Drop exact or near-duplicate findings.
- Do not invent new findings that no reviewer raised.

## Reviewer findings

{{REVIEWS}}

## Output

For EACH distinct inconsistency, output one block in EXACTLY this format:

⚠️  CLARIFICATION REQUIRED: <short title>
   ├─ Location: <artifact A> vs <artifact B>
   ├─ The Gap: <one sentence>
   ├─ Recommended Direction: <concrete remediation>
   └─ Reason Why: <which constraint it violates / why it matters>

If the reviewers found no real inconsistencies, output the single token: NO_ISSUES
```

- [ ] **Step 2: Add the config defaults** to the config block of `spec_review.sh` (after the existing `SPEC_REVIEW_NO_DETACH` line, ~L16):

```bash
SPEC_REVIEW_PANEL_CMD="${SPEC_REVIEW_PANEL_CMD:-${SCRIPT_DIR}/parallel_agent.py}"
SPEC_REVIEW_SYNTH_CLI="${SPEC_REVIEW_SYNTH_CLI:-$SPEC_REVIEW_CLI}"
SPEC_REVIEW_MERGE_TEMPLATE="${SPEC_REVIEW_MERGE_TEMPLATE:-${SCRIPT_DIR}/../prompts/spec_review_merge.md}"
SPEC_REVIEW_TIMEOUT="${SPEC_REVIEW_TIMEOUT:-600}"
```

- [ ] **Step 3: Write the failing test** — add to `tests/bats/spec_review.bats`:

```bash
@test "assemble_merge_prompt substitutes {{REVIEWS}} with the reviews block" {
    local tpl="$SANDBOX/merge.md"; printf 'MHEAD\n{{REVIEWS}}\nMTAIL\n' > "$tpl"
    source "$SCRIPT"
    run assemble_merge_prompt "$tpl" "=== REVIEWER: GEMINI ===
finding one"
    assert_success
    assert_output --partial "MHEAD"
    assert_output --partial "=== REVIEWER: GEMINI ==="
    assert_output --partial "finding one"
    assert_output --partial "MTAIL"
    refute_output --partial "{{REVIEWS}}"
}
```

- [ ] **Step 4: Run it to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "assemble_merge_prompt"`
Expected: FAIL (`assemble_merge_prompt: command not found`)

- [ ] **Step 5: Implement `assemble_merge_prompt`** in `spec_review.sh` (insert after `assemble_prompt`, ~L103):

```bash
# assemble_merge_prompt TEMPLATE REVIEWS_TEXT -> merge prompt on stdout.
# Substitutes {{REVIEWS}} inline with the reviewer-findings block. Mirrors
# assemble_prompt's awk substitution; bash 3.2-safe (no RETURN trap).
assemble_merge_prompt() {
    local template="$1" reviews="$2" reviewfile rc=0
    reviewfile="$(mktemp)"
    printf '%s\n' "$reviews" > "$reviewfile"
    awk -v reviewfile="$reviewfile" '
        /\{\{REVIEWS\}\}/ {
            while ((getline ln < reviewfile) > 0) print ln
            next
        }
        { print }
    ' "$template" || rc=$?
    rm -f "$reviewfile"
    return "$rc"
}
```

- [ ] **Step 6: Run it to verify it passes**

Run: `bats tests/bats/spec_review.bats -f "assemble_merge_prompt"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add configs/claude/prompts/spec_review_merge.md configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): add merge template, config seams, assemble_merge_prompt"
```

---

### Task 2: `parse_panel_json` — extract successful agent outputs

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh` (new function after `assemble_merge_prompt`)
- Test: `tests/bats/spec_review.bats`

**Interfaces:**
- Consumes: `parallel_agent.py --json` output shape `{"agents": {NAME: {"status": "...", "output": "..."}}}` (status `"complete"` = success; from `runners.py:_collect_output`).
- Produces: `parse_panel_json JSON_FILE BLOCKS_OUT RAW_OUT` reads JSON from a file (the heredoc occupies stdin); writes labeled blocks (`=== REVIEWER: NAME ===\n<output>\n\n`) to `BLOCKS_OUT`, raw outputs joined by blank lines to `RAW_OUT`; prints `"<count>\t<all_no_issues 0|1>"` to stdout. `all_no_issues=1` iff ≥1 successful agent and NONE of their outputs contain `CLARIFICATION REQUIRED`.

- [ ] **Step 1: Write the failing test** — first add the `_panel_json` helper at
file scope in `tests/bats/spec_review.bats` (next to `_fake_reviewer`), so tests
can synthesize panel JSON fixtures:

```bash
_panel_json() {  # emit a parallel_agent.py-style JSON doc; args: "name|status|output"
    python3 - "$@" <<'PY'
import json, sys
agents = {}
for spec in sys.argv[1:]:
    name, status, output = spec.split("|", 2)
    agents[name] = {"status": status, "output": output}
print(json.dumps({"agents": agents}))
PY
}
```

Then the tests (note: `run CMD < file` redirects the function's stdin — no
`bash -c` / `declare -f` gymnastics needed):

```bash
@test "parse_panel_json reports count, all-no-issues flag, and writes blocks" {
    source "$SCRIPT"
    _panel_json "gemini|complete|⚠️  CLARIFICATION REQUIRED: A" \
                "cursor|complete|NO_ISSUES" \
                "codex|failed|exit 1 boom" > "$SANDBOX/fx.json"
    run parse_panel_json "$SANDBOX/fx.json" "$SANDBOX/blocks" "$SANDBOX/raw"
    assert_success
    assert_output "2	0"                       # 2 successful (gemini,cursor); not all-no-issues
    grep -q "=== REVIEWER: GEMINI ===" "$SANDBOX/blocks"
    grep -q "CLARIFICATION REQUIRED: A" "$SANDBOX/blocks"
}

@test "parse_panel_json flags all-no-issues when no CLARIFICATION present" {
    source "$SCRIPT"
    _panel_json "gemini|complete|NO_ISSUES" "cursor|complete|NO_ISSUES" > "$SANDBOX/fx.json"
    run parse_panel_json "$SANDBOX/fx.json" "$SANDBOX/b" "$SANDBOX/r"
    assert_success
    assert_output "2	1"
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "parse_panel_json"`
Expected: FAIL (`parse_panel_json: command not found`)

- [ ] **Step 3: Implement `parse_panel_json`** (insert after `assemble_merge_prompt`):

```bash
# parse_panel_json JSON_FILE BLOCKS_OUT RAW_OUT  (--json read from a file)
# -> stdout: "<count>\t<all_no_issues 0|1>"; writes labeled blocks + raw outputs.
# Fail-open: a malformed JSON doc yields count 0 (caller falls back).
parse_panel_json() {
    python3 - "$1" "$2" "$3" <<'PY'
import json, sys
json_file, blocks_path, raw_path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    text = open(json_file).read()
except Exception:
    text = ""
try:
    data = json.loads(text)
except Exception:
    # tolerate console preamble/trailing noise around the JSON object
    i, j = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[i:j + 1]) if i != -1 and j != -1 else {}
    except Exception:
        data = {}
agents = data.get("agents", {}) or {}
ok = [(n, (a.get("output") or "").strip())
      for n, a in sorted(agents.items())
      if a.get("status") == "complete" and (a.get("output") or "").strip()]
all_ni = bool(ok) and all("CLARIFICATION REQUIRED" not in o for _, o in ok)
with open(blocks_path, "w") as f:
    for n, o in ok:
        f.write("=== REVIEWER: %s ===\n%s\n\n" % (n.upper(), o))
with open(raw_path, "w") as f:
    f.write("\n\n".join(o for _, o in ok))
print("%d\t%d" % (len(ok), 1 if all_ni else 0))
PY
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `bats tests/bats/spec_review.bats -f "parse_panel_json"`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): parse_panel_json extracts successful agent outputs"
```

---

### Task 3: `run_synthesizer` — merge labeled reviews via the single-CLI seam

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh` (new function after `run_reviewer`)
- Test: `tests/bats/spec_review.bats`

**Interfaces:**
- Consumes: labeled reviews block on **stdin**; `assemble_merge_prompt`, `resolve_review_model`, `SPEC_REVIEW_SYNTH_CLI`, `SPEC_REVIEW_MERGE_TEMPLATE`.
- Produces: `run_synthesizer` → merged findings (synth CLI stdout). Non-zero exit propagates so callers can fall back.

- [ ] **Step 1: Write the failing test**

```bash
_fake_synth() {  # stub synth CLI that echoes a merged finding, proving it ran
    cat > "$SANDBOX/synth" <<'STUB'
#!/usr/bin/env bash
cat >/dev/null   # consume the merge prompt on stdin
printf '⚠️  CLARIFICATION REQUIRED: Merged\n   └─ Reason Why: deduped\n'
STUB
    chmod +x "$SANDBOX/synth"
}

@test "run_synthesizer merges reviews through the synth seam + merge template" {
    _fake_synth
    source "$SCRIPT"
    SPEC_REVIEW_SYNTH_CLI="$SANDBOX/synth" \
    SPEC_REVIEW_MERGE_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review_merge.md" \
        run run_synthesizer <<< "=== REVIEWER: GEMINI ===
finding one"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Merged"
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "run_synthesizer"`
Expected: FAIL (`run_synthesizer: command not found`)

- [ ] **Step 3: Implement `run_synthesizer`** (insert after `run_reviewer`, ~L143):

```bash
# run_synthesizer  (labeled reviews block on stdin) -> merged findings on stdout.
# Builds the merge prompt from the template and pipes it to the single-CLI synth
# seam. Errors propagate so run_panel can fall back to a labeled concat.
run_synthesizer() {
    local reviews prompt model
    reviews="$(cat)"
    prompt="$(assemble_merge_prompt "$SPEC_REVIEW_MERGE_TEMPLATE" "$reviews")"
    model="$(resolve_review_model)"
    local cli_args=()
    [[ -n "$model" ]] && cli_args+=(--model "$model")
    cli_args+=(-p "Merge the reviewer findings above into one deduped list per the instructions; output only the specified blocks or NO_ISSUES.")
    printf '%s' "$prompt" | "$SPEC_REVIEW_SYNTH_CLI" "${cli_args[@]}"
}
```

Note: `resolve_review_model` only emits a model when `SPEC_REVIEW_CLI == "agy"` (it reads `model_tiers.antigravity.advanced`). With a stubbed synth CLI it returns empty and no `--model` is passed — the test stub ignores args regardless.

- [ ] **Step 4: Run to verify it passes**

Run: `bats tests/bats/spec_review.bats -f "run_synthesizer"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): run_synthesizer merges panel reviews via seam"
```

---

### Task 4: `run_panel` — orchestrate panel call + aggregation + fallbacks

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh` (new function after `run_synthesizer`)
- Test: `tests/bats/spec_review.bats`

**Interfaces:**
- Consumes: assembled prompt (arg); `SPEC_REVIEW_PANEL_CMD`, `SPEC_REVIEW_TIMEOUT`, `parse_panel_json`, `run_synthesizer`, `run_reviewer`.
- Produces: `run_panel PROMPT` → formatted-ready findings text (raw blocks or `NO_ISSUES`) on stdout. Routing: 0 agents → `run_reviewer` fallback; all-no-issues → `NO_ISSUES`; 1 agent → that output; ≥2 → `run_synthesizer` (on synth failure → labeled concat).

- [ ] **Step 1: Write the failing tests**

```bash
_fake_panel() {  # stub parallel_agent.py emitting canned JSON from $PANEL_FIXTURE
    cat > "$SANDBOX/panel" <<'STUB'
#!/usr/bin/env bash
# prompt arrives as the trailing positional arg; ignore it. Emit canned JSON.
cat "$PANEL_FIXTURE"
STUB
    chmod +x "$SANDBOX/panel"
}

@test "run_panel: >=2 agents are merged by the synthesizer" {
    _fake_panel; _fake_synth
    _panel_json "gemini|complete|⚠️  CLARIFICATION REQUIRED: A" \
                "cursor|complete|⚠️  CLARIFICATION REQUIRED: B" > "$SANDBOX/fx.json"
    source "$SCRIPT"
    PANEL_FIXTURE="$SANDBOX/fx.json" \
    SPEC_REVIEW_PANEL_CMD="$SANDBOX/panel" \
    SPEC_REVIEW_SYNTH_CLI="$SANDBOX/synth" \
    SPEC_REVIEW_MERGE_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review_merge.md" \
        run run_panel "the assembled prompt"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Merged"
}

@test "run_panel: exactly 1 agent passes through without a synth call" {
    _fake_panel
    _panel_json "gemini|complete|⚠️  CLARIFICATION REQUIRED: Solo" > "$SANDBOX/fx.json"
    source "$SCRIPT"
    PANEL_FIXTURE="$SANDBOX/fx.json" \
    SPEC_REVIEW_PANEL_CMD="$SANDBOX/panel" \
    SPEC_REVIEW_SYNTH_CLI="/bin/false" \
        run run_panel "p"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Solo"
}

@test "run_panel: all NO_ISSUES short-circuits to NO_ISSUES (no synth call)" {
    _fake_panel
    _panel_json "gemini|complete|NO_ISSUES" "cursor|complete|NO_ISSUES" > "$SANDBOX/fx.json"
    source "$SCRIPT"
    PANEL_FIXTURE="$SANDBOX/fx.json" \
    SPEC_REVIEW_PANEL_CMD="$SANDBOX/panel" \
    SPEC_REVIEW_SYNTH_CLI="/bin/false" \
        run run_panel "p"
    assert_success
    assert_output --partial "NO_ISSUES"
}

@test "run_panel: panel failure falls back to the single-CLI reviewer" {
    _fake_reviewer    # provides $SANDBOX/agy
    source "$SCRIPT"
    SPEC_REVIEW_PANEL_CMD="/bin/false" \
    SPEC_REVIEW_CLI="$SANDBOX/agy" \
        run run_panel "p"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Migration"   # from the agy stub
}

@test "run_panel: synthesizer failure falls back to labeled concat" {
    _fake_panel
    _panel_json "gemini|complete|⚠️  CLARIFICATION REQUIRED: A" \
                "cursor|complete|⚠️  CLARIFICATION REQUIRED: B" > "$SANDBOX/fx.json"
    source "$SCRIPT"
    PANEL_FIXTURE="$SANDBOX/fx.json" \
    SPEC_REVIEW_PANEL_CMD="$SANDBOX/panel" \
    SPEC_REVIEW_SYNTH_CLI="/bin/false" \
    SPEC_REVIEW_MERGE_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review_merge.md" \
        run run_panel "p"
    assert_success
    assert_output --partial "=== REVIEWER: GEMINI ==="
    assert_output --partial "CLARIFICATION REQUIRED: A"
    assert_output --partial "CLARIFICATION REQUIRED: B"
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `bats tests/bats/spec_review.bats -f "run_panel"`
Expected: FAIL (`run_panel: command not found`)

- [ ] **Step 3: Implement `run_panel`** (insert after `run_synthesizer`):

```bash
# run_panel PROMPT -> findings text (raw blocks or NO_ISSUES) on stdout.
# Fans the prompt to the parallel-agent panel (excluding the author, claude),
# then aggregates. Any panel/JSON problem falls back to the single-CLI seam;
# a synth failure falls back to a labeled concat so findings are never lost.
run_panel() {
    local prompt="$1" tmpjson tmpblocks tmpraw meta count all_ni out
    tmpjson="$(mktemp)"; tmpblocks="$(mktemp)"; tmpraw="$(mktemp)"
    # Prompt is passed as the trailing positional arg (parallel_agent.py reads no
    # stdin); `--` guards a prompt that might start with '-'. Planning artifacts
    # are bounded, so ARG_MAX is not a concern.
    if ! "$SPEC_REVIEW_PANEL_CMD" --json --no-claude --no-synthesize \
            --no-stream --timeout "$SPEC_REVIEW_TIMEOUT" -- "$prompt" \
            > "$tmpjson" 2>/dev/null
    then
        rm -f "$tmpjson" "$tmpblocks" "$tmpraw"
        run_reviewer "$prompt"; return $?
    fi
    meta="$(parse_panel_json "$tmpjson" "$tmpblocks" "$tmpraw" 2>/dev/null)" || meta="0	0"
    count="${meta%%$'\t'*}"; all_ni="${meta##*$'\t'}"
    if [[ -z "$count" || "$count" == "0" ]]; then
        rm -f "$tmpjson" "$tmpblocks" "$tmpraw"
        run_reviewer "$prompt"; return $?
    fi
    if [[ "$all_ni" == "1" ]]; then
        rm -f "$tmpjson" "$tmpblocks" "$tmpraw"
        printf 'NO_ISSUES\n'; return 0
    fi
    if [[ "$count" == "1" ]]; then
        cat "$tmpraw"
    else
        if ! out="$(run_synthesizer < "$tmpblocks")"; then
            out="$(cat "$tmpblocks")"   # synth failed: keep labeled findings
        fi
        printf '%s\n' "$out"
    fi
    rm -f "$tmpjson" "$tmpblocks" "$tmpraw"
    return 0
}
```

- [ ] **Step 4: Run to verify they pass**

Run: `bats tests/bats/spec_review.bats -f "run_panel"`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): run_panel orchestrates panel + synthesis + fallbacks"
```

---

### Task 5: Rewire `review()` and `_silent_review_inline()` to use `run_panel`

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh` (`review()` ~L208-217; `_silent_review_inline()` ~L222-240; status line ~L213)
- Test: `tests/bats/spec_review.bats`

**Interfaces:**
- Consumes: `run_panel`. Both entry points now route through the panel (decision #4: parallel everywhere, incl. the hook).

- [ ] **Step 1: Write the failing test** (on-demand path uses the panel):

```bash
@test "on-demand review routes through the parallel panel" {
    _fake_panel
    _panel_json "gemini|complete|⚠️  CLARIFICATION REQUIRED: PanelPath" > "$SANDBOX/fx.json"
    mkdir -p "$SANDBOX/specs/001"; : > "$SANDBOX/specs/001/spec.md"; : > "$SANDBOX/specs/001/plan.md"
    PANEL_FIXTURE="$SANDBOX/fx.json" \
    SPEC_REVIEW_PANEL_CMD="$SANDBOX/panel" \
    SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" "$SANDBOX"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: PanelPath"
}

@test "silent mode routes through the panel and writes feedback (NO_DETACH)" {
    _fake_panel
    _panel_json "gemini|complete|⚠️  CLARIFICATION REQUIRED: HookPanel" > "$SANDBOX/fx.json"
    mkdir -p "$SANDBOX/specs/001"; printf 'a\n' > "$SANDBOX/specs/001/spec.md"; printf 'b\n' > "$SANDBOX/specs/001/plan.md"
    PANEL_FIXTURE="$SANDBOX/fx.json" \
    SPEC_REVIEW_PANEL_CMD="$SANDBOX/panel" \
    SPEC_REVIEW_NO_DETACH=1 SPEC_REVIEW_STATE="$SANDBOX/.spec-review" \
    SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" --silent "$SANDBOX"
    assert_success
    assert [ -f "$SANDBOX/.spec-review/feedback.md" ]
    grep -q "CLARIFICATION REQUIRED: HookPanel" "$SANDBOX/.spec-review/feedback.md"
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `bats tests/bats/spec_review.bats -f "panel"`
Expected: FAIL (current `review`/`_silent_review_inline` call `run_reviewer`, which has no panel stub → error or wrong output)

- [ ] **Step 3: Rewire `review()`** — replace its body's reviewer call and status line. Change:

```bash
    echo "[spec-review] Cross-referencing project artifacts with Antigravity (agy)…"
    local prompt raw; prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" "${arts[@]+"${arts[@]}"}")"
    raw="$(run_reviewer "$prompt")"
```

to:

```bash
    echo "[spec-review] Cross-referencing project artifacts with the parallel agent panel…"
    local prompt raw; prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" "${arts[@]+"${arts[@]}"}")"
    raw="$(run_panel "$prompt")"
```

- [ ] **Step 4: Rewire `_silent_review_inline()`** — change the reviewer call:

```bash
    if ! raw="$(run_reviewer "$prompt" 2>>"$state/error.log")"; then
```

to:

```bash
    if ! raw="$(run_panel "$prompt" 2>>"$state/error.log")"; then
```

(The surrounding fail-open / hash-recording / atomic-write logic is unchanged — `run_panel` already falls back internally, and a total failure still returns non-zero → hook fails open.)

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `bats tests/bats/spec_review.bats -f "panel"`
Expected: PASS

- [ ] **Step 6: Run the FULL spec_review suite (no regressions)**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (all tests — existing seam/hook tests still green because `run_reviewer` and the fallbacks are intact)

- [ ] **Step 7: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): route on-demand + hook review through the panel"
```

---

### Task 6: Docs + skill + final verification

**Files:**
- Modify: `.skillshare/skills/spec-review/SKILL.md`, `configs/claude/scripts/spec_review.sh` (header comment ~L1-7), `configs/gemini/GEMINI.md`, `configs/cursor/rules/spec-review.mdc`
- Test: `tests/bats/spec_review.bats` (existing SKILL.md frontmatter test must still pass), shellcheck

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `SKILL.md`** — replace the description and intro so they describe the panel. New frontmatter description:

```markdown
description: Cross-reference spec/plan/tasks artifacts for internal consistency using the parallel-agent panel (gemini/cursor/codex/antigravity, excluding the author) and a synthesized deduped findings list. Analysis-only, never edits. Works with speckit (spec.md/plan.md/tasks.md) and superpowers layouts; auto-discovers or takes explicit paths.
```

Update the body heading/intro from "Antigravity cross-reference" / "A second model (Antigravity / `agy`)" to: "Runs the parallel-agent panel (excluding the author) and synthesizes a single deduped findings list." Update the closing line `Requires the `agy` CLI` → `Requires `parallel_agent.py` plus at least one non-Claude agent CLI (falls back to a single `agy` review).`

- [ ] **Step 2: Update the `spec_review.sh` header comment** (~L2-5) to say it fans out to the parallel-agent panel and synthesizes, keeping the `SPEC_REVIEW_CLI` seam as synthesizer + fallback.

- [ ] **Step 3: Update `configs/gemini/GEMINI.md` and `configs/cursor/rules/spec-review.mdc`** — any sentence describing spec-review as an "Antigravity/agy" single-reviewer → "parallel-agent panel (excluding the author), synthesized". (grep each for `spec.review`/`agy` and adjust the description lines only.)

- [ ] **Step 4: Run the SKILL.md frontmatter test**

Run: `bats tests/bats/spec_review.bats -f "SKILL.md"`
Expected: PASS (valid frontmatter, still points at the engine)

- [ ] **Step 5: Shellcheck + full suite**

Run: `shellcheck configs/claude/scripts/spec_review.sh && bats tests/bats/spec_review.bats`
Expected: shellcheck clean (no new findings); all bats PASS

- [ ] **Step 6: Commit**

```bash
git add .skillshare/skills/spec-review/SKILL.md configs/claude/scripts/spec_review.sh configs/gemini/GEMINI.md configs/cursor/rules/spec-review.mdc
git commit -m "docs(spec-review): describe parallel-agent panel engine"
```

---

## Manual end-to-end verification (after all tasks)

1. **On-demand, live panel** (needs ≥1 non-Claude agent authenticated):
   `configs/claude/scripts/spec_review.sh --spec docs/superpowers/specs/2026-06-28-spec-review-parallel-agents-design.md`
   → status line says "parallel agent panel"; output is one deduped block list or `NO_ISSUES`.
2. **Fallback (no panel)**: `SPEC_REVIEW_PANEL_CMD=/bin/false SPEC_REVIEW_CLI=agy configs/claude/scripts/spec_review.sh --spec … --plan …` → single `agy` review still works.
3. **Hook**: edit two artifacts under a `specs/<n>/` dir, run `spec_review.sh --silent .`, confirm `.spec-review/feedback.md` is written; a second unchanged run is a no-op (hash-gated).
4. Confirm `git grep -n "Antigravity (agy)" configs/claude/scripts/spec_review.sh` returns nothing (status line updated).
