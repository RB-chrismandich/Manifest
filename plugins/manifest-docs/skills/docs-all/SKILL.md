---
name: docs-all
description: Run docs-improve-readme, docs-generate-diagrams, and docs-improve in one pass as sub-agents, bracketed by a docs_lint.py measurement so the report shows a real line-count delta. Use to refresh the whole doc set at once.
---

# All-in-One Documentation Refresh

Orchestrate the three docs skills in a single pass and report a measured
result. Concision rules: `configs/claude/references/doc-concision.md`.

## When to use

- Refreshing README, diagrams, and the docs audit together after a meaningful
  change.
- You don't want to remember the right order to run them in.

## Task

1. **Measure the baseline.** Before dispatching anything:

   ```bash
   python3 configs/claude/scripts/docs_lint.py . --json /tmp/docs-all-before.json
   ```

   Without a baseline the final report can only assert improvement, not show
   it.

2. **Decide the order for this run.** Inspect what changed (recent diff, or the
   target path) and choose an order, honoring the one hard dependency:
   **`/manifest-docs:docs-improve` runs last** — its audit must see the README and diagram
   updates the other two produce.

   - **Default (no strong signal):** `docs-improve-readme` →
     `docs-generate-diagrams` → `docs-improve`.
   - Changes in architecture/module structure or imports → run
     `docs-generate-diagrams` early.
   - Changes mostly in prose/onboarding → run `/manifest-docs:docs-improve-readme` early.
   - `--order a,b,c` from the user is used verbatim; warn if it violates the
     dependency.

3. **Dispatch each docs skill as a sub-agent**, one per skill, passing the
   target path. Independent skills may run concurrently; `/manifest-docs:docs-improve` waits.

4. **Continue on failure.** Capture a failing sub-agent's error and still run
   the rest — never abort the whole run because one failed.

5. **Re-measure and report the delta.**

   ```bash
   python3 configs/claude/scripts/docs_lint.py . --json /tmp/docs-all-after.json
   ```

   ```text
   docs-all report
   Order: readme → diagrams → improve   (reason: <signal | default>)
   - docs-improve-readme    : success — README 464 → 186 lines
   - docs-generate-diagrams : success — split into docs/diagrams/ (5 pages)
   - docs-improve           : failed  — <error>
   Caps:  10 over → 2 over | Lines: 6,140 → 3,880 | Fluff: 20 → 3
   Still over: docs/COMMANDS.md (generated), docs/CONFIGURATION.md (not split)
   ```

   The report MUST state the order used, why, each sub-skill's outcome, and the
   before/after cap counts. Docs still over cap are named, not omitted.

## Notes

- This skill writes no files and runs no shell script beyond `docs_lint.py` —
  everything else is sub-agent orchestration.
- If one of the three skills is unavailable, run the others and report the gap.

## Sub-agent dispatch

This skill always fans out: one sub-agent per docs sub-skill. Pick the mechanism
per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on
Claude, or `manifest parallel-agent` / inline on other assistants. Dispatched
sub-agents execute their task directly and do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`) — pass
the model explicitly; inheriting the session's model bills premium rates for
fan-out work.
