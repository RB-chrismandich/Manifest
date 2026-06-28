# Spec-Review via the Parallel-Agent Panel — Design

**Date**: 2026-06-28
**Status**: Draft (pending approval)
**Topic**: Update the `spec-review` skill to cross-reference planning artifacts with
the multi-agent parallel panel instead of a single Antigravity (`agy`) reviewer.

## Context

`spec-review` runs an independent, analysis-only consistency check across a
project's planning artifacts (speckit `spec.md`/`plan.md`/`tasks.md` or the
superpowers `*-design.md` + `plans/*.md` layout). Today `spec_review.sh` pipes the
assembled artifact prompt to **one** reviewer CLI via the injectable
`SPEC_REVIEW_CLI` seam (default `agy`). A single model means a single blind spot:
whatever that one reviewer misses goes unreported.

This change fans the review out across the existing parallel-agent panel
(`parallel_agent.py`: claude/gemini/cursor/codex/antigravity) and synthesizes
their findings into one deduped list — more independent eyes, higher-signal
output, fewer single-model misses. The skill stays analysis-only (never edits
artifacts).

### Decisions (locked with user)
1. **Integration** — route through `parallel_agent.py` (reuse the panel,
   rate-limiting, credit-fallback); keep the `SPEC_REVIEW_CLI` single-agent seam.
2. **Panel** — exclude the author, Claude (`--no-claude`); reviewers are the other
   enabled agents (gemini/cursor/codex/antigravity). Claude reviewing its own spec
   is weak signal.
3. **Aggregation** — always synthesize the panel's findings into one deduped
   `CLARIFICATION REQUIRED` list. The orchestrator's built-in synthesis is gated on
   a word-overlap `consensus_score < 0.50` (`synthesis.py:47`) — non-deterministic
   for free-form findings — so spec-review does its own deterministic merge.
4. **Hook mode** — parallel everywhere: the detached save-hook uses the full panel
   too, relying on its existing detach + hash-gate + single-flight + fail-open
   machinery to absorb the added latency.

## Architecture

`spec_review.sh` keeps its structure (assemble → review → format; on-demand +
detached hook). A new `run_panel` becomes the default review engine. `run_reviewer`
(the single-CLI seam) is retained for two narrower jobs: the **synthesizer** step
and the **fallback** path. Both `review()` (on-demand) and `_silent_review_inline()`
(hook) call `run_panel`.

### Flow: `run_panel PROMPT`
1. `assemble_prompt` (unchanged) → artifacts + template → combined prompt.
2. Invoke the panel:
   `$SPEC_REVIEW_PANEL_CMD --json --no-claude --no-synthesize --no-stream --timeout <T>`
   with the prompt on stdin.
   - `--no-claude` → decision #2.
   - `--no-synthesize` → we synthesize ourselves (decision #3); avoids the
     consensus-gated, non-deterministic built-in synthesis and a redundant call.
3. Parse JSON (python3 helper, mirroring `resolve_review_model`): collect
   `agents[name].output` for every agent whose `status == "complete"`.
4. Aggregate by successful-agent count:
   - **all outputs are `NO_ISSUES`** → emit `NO_ISSUES` (short-circuit; no merge call).
   - **≥2 agents** → `run_synthesizer`: feed the N labeled reviews to the single-CLI
     seam with the merge template → one deduped block list.
   - **exactly 1 agent** → use its output directly (no merge needed).
   - **0 agents** → fall back to single-CLI `run_reviewer` (a full review via the seam).
5. `format_findings` (unchanged) → `tree` or `json`.

### Data flow
```
artifacts → assemble_prompt → parallel_agent.py (N agents, --no-claude, --json)
          → parse_panel_outputs → [run_synthesizer over N reviews] → format_findings
```
Hook mode wraps this in the existing detach / single-flight lock / hash-gate /
fail-open path — unchanged.

## Components

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `run_panel(prompt)` | Orchestrate panel call + aggregation; pick merge / passthrough / fallback. | panel cmd, `parse_panel_outputs`, `run_synthesizer`, `run_reviewer` |
| `parse_panel_outputs(json)` | Extract successful agents' outputs from `--json`. | python3/json |
| `run_synthesizer(reviews)` | Merge N labeled reviews into one deduped block list via the single-CLI seam + merge template. | `SPEC_REVIEW_SYNTH_CLI`, merge template |
| `run_reviewer(prompt)` | Unchanged single-CLI full review; now also the 0-agent fallback. | `SPEC_REVIEW_CLI` |
| `format_findings` / `assemble_prompt` / hook funcs | Unchanged. | — |

### New configuration seams
- `SPEC_REVIEW_PANEL_CMD` — default `<script_dir>/parallel_agent.py`; injectable so
  tests can stub a fake panel that emits canned JSON.
- `SPEC_REVIEW_SYNTH_CLI` — default = `SPEC_REVIEW_CLI` (the synthesizer CLI).
- New template `configs/claude/prompts/spec_review_merge.md` — instructs the
  synthesizer to dedupe/merge the N reviews, emitting the **same** output contract
  (`CLARIFICATION REQUIRED` blocks or `NO_ISSUES`) as `spec_review.md`.

Panel args (`--no-claude --no-synthesize --no-stream`) are hardcoded (YAGNI: only
`PANEL_CMD` needs to be injectable for tests).

## Error handling (fail-open preserved)
- Panel command missing / non-zero exit / empty or unparseable JSON → fall back to
  single-CLI `run_reviewer`.
- Synthesizer step fails → fall back to **labeled per-agent concatenation** so no
  findings are lost.
- Hook mode: any failure writes nothing and does **not** record the content hash, so
  the same content is retried on the next save (preserves issue #317 contract).
- Timeout: pass a generous per-agent timeout (default 600s) to `parallel_agent.py`;
  the hook is detached, so latency never blocks the agent loop.

## Testing
Existing seam-based bats keep passing because `run_reviewer` and the
`SPEC_REVIEW_CLI` seam are retained. New tests stub `parallel_agent.py` via
`SPEC_REVIEW_PANEL_CMD` (a script emitting canned `--json`) and a synth CLI via
`SPEC_REVIEW_SYNTH_CLI`, covering:
- ≥2 agents → synthesizer merge is invoked, output formatted.
- exactly 1 agent → passthrough (no merge call).
- all `NO_ISSUES` → clean short-circuit, no merge call.
- panel fails / empty JSON → single-CLI `run_reviewer` fallback.
- synthesizer fails → labeled per-agent concat fallback (findings retained).
- hook (`--silent` with `NO_DETACH`) still fail-open + hash-gated using the panel.

## Docs / skill
- `SKILL.md` — description + body: "uses the parallel-agent panel (independent of
  the author) and synthesizes a deduped findings list."
- `spec_review.sh` — header comment + the `[spec-review] Cross-referencing … with
  Antigravity (agy)` status line → "with the parallel agent panel".
- `configs/gemini/GEMINI.md` and `configs/cursor/rules/spec-review.mdc` engine
  references updated.

## Out of scope
- No consensus-filter / finding-matching logic (decision #3 chose synthesis).
- No change to `parallel_agent.py` itself (used as-is via its CLI).
- No change to artifact discovery or the output contract.

## Verification
1. `shellcheck configs/claude/scripts/spec_review.sh`; `bats tests/bats/spec_review.bats`.
2. On-demand: `spec_review.sh --spec … --plan …` → panel runs `--no-claude`, output
   is one deduped block list (or `NO_ISSUES`).
3. Hook: edit two artifacts, confirm detached run uses the panel and writes
   `.spec-review/feedback.md`, second unchanged save is a no-op.
4. Fallbacks: force panel cmd to a non-zero stub → single-CLI path; force synth CLI
   to fail → labeled concat.
