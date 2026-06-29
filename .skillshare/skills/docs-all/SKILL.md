---
name: docs-all
description: Run docs-readme, docs-diagrams, and docs-improve in one command, dispatching each as a sub-agent and returning a consolidated report. Use to refresh the whole doc set at once.
---

# All-in-One Documentation Refresh

Orchestrate the three existing documentation skills in a single pass instead of
running them by hand. Each runs as an independent sub-agent; results are merged
into one report.

## When to use

- You want to refresh README, architecture diagrams, and the Diataxis docs audit
  together after a meaningful change.
- You don't want to remember the right order to run them in.

## Task

1. **Decide the order for this run.** Inspect what changed (recent diff / the
   target path) and choose an order, honoring the one hard dependency:
   **`docs-improve` runs last** (its quality audit should see the README and
   diagram updates the other two produce).

   - **Default precedence (fallback when no strong signal):**
     `docs-readme` → `docs-diagrams` → `docs-improve`.
   - **Signal-based adjustments:**
     - Changes concentrated in architecture/module structure or imports →
       prioritize `docs-diagrams` early.
     - Changes mostly in prose/onboarding → prioritize `docs-readme` early.
     - Either way, keep `docs-improve` last.
   - If the user passed `--order a,b,c`, use it verbatim (still keep the
     dependency in mind and warn if it is violated).

2. **Dispatch each docs skill as a sub-agent** using the Task tool, one per
   skill, passing through the target path. Run them per the order from step 1.
   Independent skills may run concurrently; `docs-improve` waits for the others.

3. **Continue on failure.** If one sub-agent fails, capture its error and still
   run the remaining skills — never abort the whole run because one failed.

4. **Emit one consolidated report:**

   ```text
   docs-all report
   Order: <a> → <b> → <c>   (reason: <signal | default fallback>)
   - docs-readme    : success — <1-line summary>
   - docs-diagrams  : success — <1-line summary>
   - docs-improve   : failed  — <error>
   ```

   The report MUST state the order used, why that order was chosen, and each
   sub-skill's outcome (FR-010/FR-011).

## Notes

- This skill writes no files itself and runs no shell script — it is pure
  sub-agent orchestration over `docs-readme`, `docs-diagrams`, `docs-improve`.
- If one of the three skills is unavailable, run the others and report the gap.
- Verification scenario: see `specs/002-new-agent-skills/quickstart.md` (docs-all
  section) for how to confirm ordering, rationale, and failure-surfacing.

## Sub-agent dispatch

This skill always fans out: dispatch one sub-agent per docs sub-skill (docs-readme, docs-diagrams, docs-improve) and merge their reports. Pick the mechanism per the shared Sub-Agent Selection Rules (`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `parallel_agent.py` / inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.
