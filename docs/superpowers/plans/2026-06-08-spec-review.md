# /spec-review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An analysis-only `/spec-review` skill + reusable engine script that cross-references spec/plan/tasks artifacts for consistency via the `gemini` CLI, with an optional fail-open, content-hash-debounced, detached PostToolUse save hook.

**Architecture:** One front-end-agnostic engine (`spec_review.sh`) + a prompt template drive `gemini -p`; a `/spec-review` SKILL.md is the on-demand entry point; a PostToolUse hook runs `spec_review.sh --silent` which gates on a content hash + single-flight lock and detaches the `gemini` call so it never stalls the agent loop. Gemini is invoked through one injectable seam (`SPEC_REVIEW_GEMINI`) so tests never hit the network.

**Tech Stack:** Bash (3.2-compatible, `set -euo pipefail`), `gemini` CLI, `shasum`, bats (bats-support/bats-assert), Markdown, JSON (settings).

---

## Reference: engine contract (used consistently across tasks)

`configs/claude/scripts/spec_review.sh` defines these functions and a sourcing guard so bats can source it and test functions in isolation:

```bash
SPEC_REVIEW_GEMINI="${SPEC_REVIEW_GEMINI:-gemini}"   # injectable engine seam
SPEC_REVIEW_TEMPLATE="${SPEC_REVIEW_TEMPLATE:-<script_dir>/../prompts/spec_review.md}"
SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE:-.spec-review}" # runtime dir (gitignored)
SPEC_REVIEW_NO_DETACH="${SPEC_REVIEW_NO_DETACH:-}"     # set => run gemini inline (tests)

discover_artifacts ROOT        # prints "role\tpath" lines: spec/plan/tasks (tasks optional)
assemble_prompt TEMPLATE FILE… # prints the full prompt (template + role-labelled artifacts)
run_gemini PROMPT              # pipes PROMPT to "$SPEC_REVIEW_GEMINI" -p "<instruction>"; prints raw output
format_findings RAW FORMAT     # RAW gemini output -> tree (default) or json
content_hash FILE…            # stable hash of combined artifact contents
should_run_silent ROOT         # 0/skip-reason gating: >=2 artifacts, hash changed, lock free
review ROOT FORMAT             # orchestrate: discover -> assemble -> run -> format
main "$@"                       # arg parse; guarded by [[ "${BASH_SOURCE[0]}" == "${0}" ]]
```

The sourcing guard at the bottom:

```bash
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

---

## File Structure

**Create:**
- `configs/claude/scripts/spec_review.sh` — the engine
- `configs/claude/prompts/spec_review.md` — the gemini prompt template
- `.skillshare/skills/spec-review/SKILL.md` — the `/spec-review` on-demand entry point
- `tests/bats/spec_review.bats` — engine tests

**Modify:**
- `configs/claude/settings.local.json` — append the PostToolUse hook
- `.gitignore` — add `.spec-review/`
- `docs/COMMANDS.md` — add `/spec-review` to the command reference (if present)

---

## Task 1: Scaffold engine — arg parsing, seams, sourcing guard

**Files:**
- Create: `configs/claude/scripts/spec_review.sh`
- Create: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
# tests/bats/spec_review.bats
#!/usr/bin/env bats
# Tests for configs/claude/scripts/spec_review.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/spec_review.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/spec_review.XXXXXX")
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "spec_review.sh is executable and prints usage on --help" {
    run bash "$SCRIPT" --help
    assert_success
    assert_output --partial "spec-review"
    assert_output --partial "--silent"
}

@test "spec_review.sh rejects an unknown flag" {
    run bash "$SCRIPT" --bogus
    assert_failure
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Write minimal implementation**

```bash
#!/usr/bin/env bash
# spec_review.sh — cross-reference spec/plan/tasks artifacts for consistency via
# the gemini CLI. Analysis-only: never edits artifacts. Front-end-agnostic — the
# /spec-review skill, the save hook, and any future CLI all wrap this script.
#
# Usage: spec_review.sh [--spec F] [--plan F] [--tasks F] [--silent] [--format tree|json] [ROOT]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_REVIEW_GEMINI="${SPEC_REVIEW_GEMINI:-gemini}"
SPEC_REVIEW_TEMPLATE="${SPEC_REVIEW_TEMPLATE:-${SCRIPT_DIR}/../prompts/spec_review.md}"
SPEC_REVIEW_STATE="${SPEC_REVIEW_STATE:-.spec-review}"
SPEC_REVIEW_NO_DETACH="${SPEC_REVIEW_NO_DETACH:-}"

SPEC=""; PLAN=""; TASKS=""; SILENT=false; FORMAT="tree"; ROOT="."

err() { echo "spec-review: $*" >&2; }
usage() {
    cat <<'EOF'
spec-review — cross-reference spec/plan/tasks for consistency (Gemini, analysis-only)

Usage: spec_review.sh [--spec F] [--plan F] [--tasks F] [--silent] [--format tree|json] [ROOT]

  --spec/--plan/--tasks F  explicit artifact paths (else auto-discover under ROOT)
  --silent                 hook mode: hash-gated, detached, writes .spec-review/feedback.md
  --format tree|json       output format (default: tree)
  ROOT                     project root to discover in (default: .)
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --spec)  SPEC="$2"; shift 2 ;;
            --plan)  PLAN="$2"; shift 2 ;;
            --tasks) TASKS="$2"; shift 2 ;;
            --silent) SILENT=true; shift ;;
            --format) FORMAT="$2"; shift 2 ;;
            -h|--help) usage; return 0 ;;
            -*) err "unknown flag: $1"; return 2 ;;
            *) ROOT="$1"; shift ;;
        esac
    done
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; return 0; fi
    parse_args "$@" || return $?
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): scaffold engine — arg parsing, seams, sourcing guard"
```

---

## Task 2: Artifact discovery (speckit + superpowers)

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
@test "discover_artifacts finds speckit spec/plan/tasks in a specs dir" {
    mkdir -p "$SANDBOX/specs/001-feature"
    : > "$SANDBOX/specs/001-feature/spec.md"
    : > "$SANDBOX/specs/001-feature/plan.md"
    : > "$SANDBOX/specs/001-feature/tasks.md"
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_success
    assert_output --partial "spec	$SANDBOX/specs/001-feature/spec.md"
    assert_output --partial "plan	$SANDBOX/specs/001-feature/plan.md"
    assert_output --partial "tasks	$SANDBOX/specs/001-feature/tasks.md"
}

@test "discover_artifacts finds superpowers design+plan (tasks embedded in plan)" {
    mkdir -p "$SANDBOX/docs/superpowers/specs" "$SANDBOX/docs/superpowers/plans"
    : > "$SANDBOX/docs/superpowers/specs/2026-06-08-thing-design.md"
    : > "$SANDBOX/docs/superpowers/plans/2026-06-08-thing.md"
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_success
    assert_output --partial "spec	$SANDBOX/docs/superpowers/specs/2026-06-08-thing-design.md"
    assert_output --partial "plan	$SANDBOX/docs/superpowers/plans/2026-06-08-thing.md"
    refute_output --partial "tasks	"
}

@test "discover_artifacts prints nothing when no artifacts exist" {
    source "$SCRIPT"
    run discover_artifacts "$SANDBOX"
    assert_output ""
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f discover`
Expected: FAIL — `discover_artifacts` not defined.

- [ ] **Step 3: Write minimal implementation**

Insert before `main()`:

```bash
# Print "role\tpath" lines for discovered artifacts. speckit: spec/plan/tasks.md
# (cwd or specs/<n>/). superpowers: newest *-design.md + newest plans/*.md (tasks
# are embedded in the plan, so no tasks line). Newest = name sort (date-prefixed).
discover_artifacts() {
    local root="${1:-.}" sp pl tk
    # speckit: specs/<n>/ first, then cwd
    sp=$(ls -1 "$root"/specs/*/spec.md 2>/dev/null | sort | tail -1 || true)
    [[ -z "$sp" && -f "$root/spec.md" ]] && sp="$root/spec.md"
    if [[ -n "$sp" ]]; then
        local d; d="$(dirname "$sp")"
        printf 'spec\t%s\n' "$sp"
        [[ -f "$d/plan.md" ]]  && printf 'plan\t%s\n'  "$d/plan.md"
        [[ -f "$d/tasks.md" ]] && printf 'tasks\t%s\n' "$d/tasks.md"
        return 0
    fi
    # superpowers: newest design + newest plan (tasks embedded in plan)
    sp=$(ls -1 "$root"/docs/superpowers/specs/*-design.md 2>/dev/null | sort | tail -1 || true)
    pl=$(ls -1 "$root"/docs/superpowers/plans/*.md 2>/dev/null | sort | tail -1 || true)
    [[ -n "$sp" ]] && printf 'spec\t%s\n' "$sp"
    [[ -n "$pl" ]] && printf 'plan\t%s\n' "$pl"
    return 0
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): framework-agnostic artifact discovery (speckit + superpowers)"
```

---

## Task 3: Prompt template + assembly

**Files:**
- Create: `configs/claude/prompts/spec_review.md`
- Modify: `configs/claude/scripts/spec_review.sh`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Create the prompt template (content step)**

```markdown
<!-- configs/claude/prompts/spec_review.md -->
# Project Artifact Cross-Reference

You are an independent reviewer cross-referencing a project's planning artifacts
for **internal consistency**. You did not write them. Find places where the
artifacts contradict each other or leave a decision dangerously ambiguous.

When `tasks` is absent, the task breakdown is embedded inside the plan — review
the plan's task section against the spec and plan prose.

## Artifacts

{{ARTIFACTS}}

## Output

For EACH inconsistency, output one block in EXACTLY this format:

⚠️  CLARIFICATION REQUIRED: <short title>
   ├─ Location: <artifact A> vs <artifact B>
   ├─ The Gap: <one sentence>
   ├─ Recommended Direction: <concrete remediation>
   └─ Reason Why: <which constraint it violates / why it matters>

If the artifacts are consistent, output the single token: NO_ISSUES
```

- [ ] **Step 2: Write the failing test**

```bash
@test "assemble_prompt embeds template and role-labelled artifact contents" {
    local tpl="$SANDBOX/tpl.md"; printf 'HEAD\n{{ARTIFACTS}}\nTAIL\n' > "$tpl"
    printf 'spec body here\n' > "$SANDBOX/spec.md"
    printf 'plan body here\n' > "$SANDBOX/plan.md"
    source "$SCRIPT"
    run assemble_prompt "$tpl" "spec	$SANDBOX/spec.md" "plan	$SANDBOX/plan.md"
    assert_success
    assert_output --partial "HEAD"
    assert_output --partial "=== SPEC: $SANDBOX/spec.md ==="
    assert_output --partial "spec body here"
    assert_output --partial "=== PLAN: $SANDBOX/plan.md ==="
    assert_output --partial "plan body here"
    refute_output --partial "{{ARTIFACTS}}"
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f assemble`
Expected: FAIL — `assemble_prompt` not defined.

- [ ] **Step 4: Write minimal implementation**

Insert before `main()`:

```bash
# assemble_prompt TEMPLATE "role\tpath"...  ->  full prompt on stdout
assemble_prompt() {
    local template="$1"; shift
    local artifacts="" line role path
    for line in "$@"; do
        role="${line%%$'\t'*}"; path="${line#*$'\t'}"
        artifacts+="=== ${role^^}: ${path} ==="$'\n'
        artifacts+="$(cat "$path")"$'\n\n'
    done
    # Substitute {{ARTIFACTS}} with the assembled block (awk avoids sed escaping).
    awk -v repl="$artifacts" '{gsub(/\{\{ARTIFACTS\}\}/, repl); print}' "$template"
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add configs/claude/prompts/spec_review.md configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): prompt template + role-labelled prompt assembly"
```

---

## Task 4: Gemini seam + findings formatting

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
_fake_gemini() {  # writes a stub gemini onto PATH inside SANDBOX
    cat > "$SANDBOX/gemini" <<'STUB'
#!/usr/bin/env bash
cat >/dev/null   # consume stdin
printf '⚠️  CLARIFICATION REQUIRED: Migration\n   ├─ Location: plan vs tasks\n   ├─ The Gap: zero-downtime vs destructive\n   ├─ Recommended Direction: split into 3 tasks\n   └─ Reason Why: locking violates the constraint\n'
STUB
    chmod +x "$SANDBOX/gemini"
}

@test "run_gemini pipes prompt through the injectable seam" {
    _fake_gemini
    source "$SCRIPT"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" run run_gemini "any prompt"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}

@test "format_findings tree passes structured findings through" {
    source "$SCRIPT"
    run format_findings "⚠️  CLARIFICATION REQUIRED: X" "tree"
    assert_output --partial "CLARIFICATION REQUIRED: X"
}

@test "format_findings reports clean when gemini returns NO_ISSUES" {
    source "$SCRIPT"
    run format_findings "NO_ISSUES" "tree"
    assert_success
    assert_output --partial "No inconsistencies found"
}

@test "format_findings json emits a JSON array" {
    source "$SCRIPT"
    run format_findings "NO_ISSUES" "json"
    assert_output --partial "[]"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f gemini`
Expected: FAIL — `run_gemini` not defined.

- [ ] **Step 3: Write minimal implementation**

Insert before `main()`:

```bash
# run_gemini PROMPT -> raw gemini output. stdin carries the prompt body; the -p
# instruction is short. Errors propagate (caller decides fail-open vs surface).
run_gemini() {
    local prompt="$1"
    printf '%s' "$prompt" | "$SPEC_REVIEW_GEMINI" -p "Cross-reference the artifacts above per the instructions; output only the specified blocks or NO_ISSUES."
}

# format_findings RAW FORMAT -> formatted output. NO_ISSUES -> clean message.
format_findings() {
    local raw="$1" fmt="${2:-tree}"
    if [[ -z "${raw//[[:space:]]/}" || "$raw" == *NO_ISSUES* ]]; then
        if [[ "$fmt" == "json" ]]; then echo "[]"; else echo "✓ No inconsistencies found."; fi
        return 0
    fi
    if [[ "$fmt" == "json" ]]; then
        # Minimal: wrap raw blocks as a single JSON string element (tolerant).
        printf '[%s]\n' "$(printf '%s' "$raw" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
    else
        printf '%s\n' "$raw"
    fi
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): injectable gemini seam + tree/json findings formatting"
```

---

## Task 5: Content-hash debounce + gating

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
@test "content_hash is stable for same content and differs on change" {
    printf 'a\n' > "$SANDBOX/x.md"; printf 'b\n' > "$SANDBOX/y.md"
    source "$SCRIPT"
    h1="$(content_hash "$SANDBOX/x.md" "$SANDBOX/y.md")"
    h2="$(content_hash "$SANDBOX/x.md" "$SANDBOX/y.md")"
    [ "$h1" = "$h2" ]
    printf 'b2\n' > "$SANDBOX/y.md"
    h3="$(content_hash "$SANDBOX/x.md" "$SANDBOX/y.md")"
    [ "$h1" != "$h3" ]
}

@test "should_run_silent skips when fewer than 2 artifacts" {
    mkdir -p "$SANDBOX/specs/001"; : > "$SANDBOX/specs/001/spec.md"
    source "$SCRIPT"
    SPEC_REVIEW_STATE="$SANDBOX/.spec-review" run should_run_silent "$SANDBOX"
    assert_failure
    assert_output --partial "fewer than 2 artifacts"
}

@test "should_run_silent runs on first change, skips on unchanged hash" {
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    source "$SCRIPT"
    export SPEC_REVIEW_STATE="$SANDBOX/.spec-review"
    run should_run_silent "$SANDBOX"; assert_success          # first time: changed
    run should_run_silent "$SANDBOX"; assert_failure          # unchanged hash
    assert_output --partial "unchanged"
    printf 'p2\n' > "$SANDBOX/specs/001/plan.md"
    run should_run_silent "$SANDBOX"; assert_success          # changed again
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "hash\|should_run"`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Write minimal implementation**

Insert before `main()`:

```bash
# Stable combined-content hash of the given files.
content_hash() {
    cat "$@" 2>/dev/null | shasum | awk '{print $1}'
}

# Gating for silent/hook mode. Returns 0 (run) or 1 (skip, with reason on stdout).
# Records the hash in $SPEC_REVIEW_STATE/.last-run only when it decides to run.
should_run_silent() {
    local root="${1:-.}" state="$SPEC_REVIEW_STATE"
    local paths; paths=$(discover_artifacts "$root" | cut -f2)
    local count; count=$(printf '%s\n' "$paths" | grep -c . || true)
    if [[ "$count" -lt 2 ]]; then echo "skip: fewer than 2 artifacts"; return 1; fi
    mkdir -p "$state"
    local now prev="$state/.last-run"
    # shellcheck disable=SC2086
    now="$(content_hash $paths)"
    if [[ -f "$prev" && "$(cat "$prev")" == "$now" ]]; then
        echo "skip: unchanged"; return 1
    fi
    echo "$now" > "$prev"
    return 0
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): content-hash debounce + <2-artifact gating"
```

---

## Task 6: Orchestration, silent/detached mode, fail-open, main wiring

**Files:**
- Modify: `configs/claude/scripts/spec_review.sh`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
@test "on-demand review prints findings from the mocked gemini" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" "$SANDBOX"
    assert_success
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}

@test "on-demand review on no artifacts exits 0 with nothing-to-review" {
    run bash "$SCRIPT" "$SANDBOX"
    assert_success
    assert_output --partial "nothing to review"
}

@test "silent mode writes feedback file and exits 0 (inline via NO_DETACH)" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_NO_DETACH=1 \
        SPEC_REVIEW_STATE="$SANDBOX/.spec-review" \
        SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" --silent "$SANDBOX"
    assert_success
    assert [ -f "$SANDBOX/.spec-review/feedback.md" ]
    run cat "$SANDBOX/.spec-review/feedback.md"
    assert_output --partial "CLARIFICATION REQUIRED: Migration"
}

@test "silent mode fails open: non-zero gemini still exits 0" {
    printf '#!/usr/bin/env bash\nexit 3\n' > "$SANDBOX/gemini"; chmod +x "$SANDBOX/gemini"
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    SPEC_REVIEW_GEMINI="$SANDBOX/gemini" SPEC_REVIEW_NO_DETACH=1 \
        SPEC_REVIEW_STATE="$SANDBOX/.spec-review" \
        SPEC_REVIEW_TEMPLATE="$REPO_ROOT/configs/claude/prompts/spec_review.md" \
        run bash "$SCRIPT" --silent "$SANDBOX"
    assert_success
}

@test "silent mode is a no-op on unchanged content (second run)" {
    _fake_gemini
    mkdir -p "$SANDBOX/specs/001"
    printf 's\n' > "$SANDBOX/specs/001/spec.md"
    printf 'p\n' > "$SANDBOX/specs/001/plan.md"
    local env="SPEC_REVIEW_GEMINI=$SANDBOX/gemini SPEC_REVIEW_NO_DETACH=1 SPEC_REVIEW_STATE=$SANDBOX/.spec-review SPEC_REVIEW_TEMPLATE=$REPO_ROOT/configs/claude/prompts/spec_review.md"
    env $env bash "$SCRIPT" --silent "$SANDBOX"
    rm -f "$SANDBOX/.spec-review/feedback.md"
    env $env bash "$SCRIPT" --silent "$SANDBOX"   # unchanged -> skip, no rewrite
    assert [ ! -f "$SANDBOX/.spec-review/feedback.md" ]
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "review\|silent"`
Expected: FAIL — `review`/silent wiring not implemented.

- [ ] **Step 3: Write minimal implementation**

Add `review()`, the silent path, and flesh out `main()`:

```bash
# review ROOT FORMAT -> discover, assemble, run gemini, format. Used on-demand.
review() {
    local root="${1:-.}" fmt="${2:-tree}"
    local arts=() line
    while IFS= read -r line; do [[ -n "$line" ]] && arts+=("$line"); done < <(discover_artifacts "$root")
    if [[ "${#arts[@]}" -eq 0 ]]; then echo "spec-review: nothing to review (no artifacts found)"; return 0; fi
    echo "[spec-review] Cross-referencing project artifacts with Gemini…"
    local prompt raw; prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" "${arts[@]}")"
    raw="$(run_gemini "$prompt")"
    format_findings "$raw" "$fmt"
}

# _silent_review_inline ROOT -> the actual review for hook mode, fail-open.
_silent_review_inline() {
    local root="$1" state="$SPEC_REVIEW_STATE"
    mkdir -p "$state"
    local arts=() line prompt raw
    while IFS= read -r line; do [[ -n "$line" ]] && arts+=("$line"); done < <(discover_artifacts "$root")
    prompt="$(assemble_prompt "$SPEC_REVIEW_TEMPLATE" "${arts[@]}")"
    if ! raw="$(run_gemini "$prompt" 2>>"$state/error.log")"; then
        return 0   # fail-open: gemini failed, never block
    fi
    format_findings "$raw" "tree" > "$state/feedback.md.tmp" && mv "$state/feedback.md.tmp" "$state/feedback.md"
}

run_silent() {
    local root="${1:-.}" state="$SPEC_REVIEW_STATE"
    local reason; if ! reason="$(should_run_silent "$root")"; then
        return 0   # gate said skip (fewer than 2 artifacts / unchanged)
    fi
    mkdir -p "$state"
    # Single-flight lock: skip if a review is already in flight.
    if ! mkdir "$state/.lock" 2>/dev/null; then return 0; fi
    if [[ -n "$SPEC_REVIEW_NO_DETACH" ]]; then
        _silent_review_inline "$root"; rmdir "$state/.lock" 2>/dev/null || true
    else
        # Detach so the agent loop never waits on gemini; release lock when done.
        ( _silent_review_inline "$root"; rmdir "$state/.lock" 2>/dev/null || true ) \
            >/dev/null 2>&1 &
        disown 2>/dev/null || true
    fi
    return 0
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; return 0; fi
    parse_args "$@" || return $?
    if [[ "$SILENT" == true ]]; then run_silent "$ROOT"; return 0; fi
    review "$ROOT" "$FORMAT"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (18 tests). Then `shellcheck configs/claude/scripts/spec_review.sh` — clean.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/spec_review.sh tests/bats/spec_review.bats
git commit -m "feat(spec-review): orchestration + fail-open detached silent mode with single-flight lock"
```

---

## Task 7: /spec-review skill + .gitignore

**Files:**
- Create: `.skillshare/skills/spec-review/SKILL.md`
- Modify: `.gitignore`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
@test "spec-review SKILL.md has valid frontmatter and points at the engine" {
    local skill="$REPO_ROOT/.skillshare/skills/spec-review/SKILL.md"
    assert [ -f "$skill" ]
    run head -1 "$skill"; assert_output "---"
    run grep -E '^name: spec-review' "$skill"; assert_success
    run grep -E 'spec_review\.sh' "$skill"; assert_success
}

@test ".gitignore ignores the .spec-review runtime dir" {
    run grep -E '^\.spec-review/?$' "$REPO_ROOT/.gitignore"
    assert_success
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "SKILL\|gitignore"`
Expected: FAIL — skill + ignore entry absent.

- [ ] **Step 3: Create the skill and ignore entry**

`.skillshare/skills/spec-review/SKILL.md`:

```markdown
---
name: spec-review
description: |
  Cross-reference a project's spec / plan / tasks artifacts for internal
  consistency using an independent model (Gemini), and surface structured
  remediation guidance (Location / Gap / Recommended Direction / Reason Why).
  Analysis-only — never edits artifacts. Works with both speckit
  (spec.md/plan.md/tasks.md) and superpowers (design + plan-with-embedded-tasks)
  layouts. Auto-discovers artifacts, or pass explicit paths.
---

# Spec Review (Gemini cross-reference)

Run an independent, analysis-only consistency check across the project's planning
artifacts. A second model (Gemini) reviews what Claude authored — catching
structural blind spots that self-review misses.

## How to run

```bash
# Auto-discover spec/plan/tasks under the current project and review:
~/.claude/scripts/spec_review.sh

# Explicit artifacts:
~/.claude/scripts/spec_review.sh --spec ./spec.md --plan ./plan.md --tasks ./tasks.md

# Machine-readable:
~/.claude/scripts/spec_review.sh --format json
```

Findings print as a tree of `CLARIFICATION REQUIRED` blocks, or
`✓ No inconsistencies found.` Requires the `gemini` CLI (logged in). This skill is
analysis-only; apply the recommendations yourself.
```

Append to `.gitignore`:

```gitignore

# spec-review runtime (feedback, content-hash, lock, error log)
.spec-review/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (20 tests).

- [ ] **Step 5: Commit**

```bash
git add .skillshare/skills/spec-review/SKILL.md .gitignore tests/bats/spec_review.bats
git commit -m "feat(spec-review): /spec-review skill + .spec-review gitignore"
```

---

## Task 8: PostToolUse save hook registration

**Files:**
- Modify: `configs/claude/settings.local.json`
- Test: `tests/bats/spec_review.bats`

- [ ] **Step 1: Write the failing test**

```bash
@test "settings.local.json registers the spec_review silent save hook" {
    local s="$REPO_ROOT/configs/claude/settings.local.json"
    run python3 -c "import json; d=json.load(open('$s')); cmds=[h['command'] for m in d['hooks']['PostToolUse'] for h in m['hooks']]; assert any('spec_review.sh' in c and '--silent' in c for c in cmds), cmds"
    assert_success
}

@test "settings.local.json remains valid JSON" {
    run python3 -c "import json; json.load(open('$REPO_ROOT/configs/claude/settings.local.json'))"
    assert_success
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/spec_review.bats -f "hook\|JSON"`
Expected: FAIL — hook not registered.

- [ ] **Step 3: Add the hook**

In `configs/claude/settings.local.json`, append a new object to the existing
`hooks.PostToolUse` array (sibling to the version_pin entry), preserving valid JSON:

```json
{
  "matcher": "Write|Edit",
  "hooks": [
    {
      "type": "command",
      "command": "~/.claude/scripts/spec_review.sh --silent"
    }
  ]
}
```

(The script self-gates: it discovers artifacts, skips on unchanged hash or <2
artifacts, and detaches the gemini call — so firing on every Write/Edit is cheap
and never blocks.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bats tests/bats/spec_review.bats`
Expected: PASS (22 tests). Then validate: `python3 -m json.tool configs/claude/settings.local.json >/dev/null && echo OK`.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/settings.local.json tests/bats/spec_review.bats
git commit -m "feat(spec-review): register fail-open PostToolUse save hook"
```

---

## Task 9: Docs + full-suite green + lint

**Files:**
- Modify: `docs/COMMANDS.md` (if present)

- [ ] **Step 1: Document the command**

Add a `/spec-review` row/section to `docs/COMMANDS.md` describing: independent
Gemini cross-reference of spec/plan/tasks; on-demand + optional save hook;
analysis-only; speckit + superpowers; `.spec-review/feedback.md` for silent runs.
If the repo has a command table in `CLAUDE.md`/`configs/claude/CLAUDE.md`, add a
matching row there too.

- [ ] **Step 2: Run the full suite**

Run:
```bash
bats tests/bats/spec_review.bats
bats tests/bats/                       # no regressions
shellcheck configs/claude/scripts/spec_review.sh
python3 -m json.tool configs/claude/settings.local.json >/dev/null && echo "json ok"
```
Expected: all green; shellcheck clean; JSON valid.

- [ ] **Step 3: Markdownlint the new docs**

Run: `markdownlint .skillshare/skills/spec-review/SKILL.md configs/claude/prompts/spec_review.md docs/superpowers/specs/2026-06-08-spec-review-design.md docs/superpowers/plans/2026-06-08-spec-review.md` (or the repo's configured linter; honor `.markdownlint.jsonc`). Fix violations.

- [ ] **Step 4: Commit**

```bash
git add docs/COMMANDS.md configs/claude/CLAUDE.md
git commit -m "docs(spec-review): document /spec-review command and save hook"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage:**
- Engine script, front-end-agnostic → Tasks 1–6. ✓
- Framework-agnostic discovery (speckit + superpowers, tasks-in-plan) → Task 2. ✓
- Prompt template + Location/Gap/Direction/Reason format → Tasks 3–4. ✓
- Injectable gemini seam (no network in tests) → Task 4. ✓
- Content-hash debounce + <2-artifact skip → Task 5. ✓
- Detached silent mode + single-flight lock + fail-open → Task 6. ✓
- On-demand `/spec-review` skill → Task 7. ✓
- `.gitignore` `.spec-review/` → Task 7. ✓
- PostToolUse hook registration (append to existing Write|Edit block) → Task 8. ✓
- Analysis-only (no artifact writes anywhere) → enforced across Tasks 1–6. ✓
- Tests/lint/docs → Tasks 1–9. ✓

**Type/name consistency:** Function names match the engine contract verbatim across tasks — `discover_artifacts`, `assemble_prompt`, `run_gemini`, `format_findings`, `content_hash`, `should_run_silent`, `run_silent`, `review`, `_silent_review_inline`, `main`. Env seams (`SPEC_REVIEW_GEMINI`, `SPEC_REVIEW_TEMPLATE`, `SPEC_REVIEW_STATE`, `SPEC_REVIEW_NO_DETACH`) are consistent throughout.

**Note for executor:** bats sources the script (`source "$SCRIPT"`), which relies on the sourcing guard (Task 1) so `main` does not run on source. The code uses portable `while read` loops (not `mapfile`) for bash 3.2 compatibility. `disown` is guarded with `|| true`; if it is unavailable, the `( … ) &` background plus the script's immediate return still detaches the gemini call. Confirm `tests/bats/test_helper/bats-support` and `bats-assert` exist (other suites in `tests/bats/` already use them) before running.
