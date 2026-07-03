---
name: speckit-audit-tasks
description: After /speckit-implement, audit that every task in tasks.md was genuinely completed — catch skipped tasks, stubbed work, missing tests, or unimplemented spec requirements. Runs automatically as the speckit after_implement hook; invoke directly to re-audit task completion.
---

# Speckit Implement Review

`speckit-implement` ticks tasks done as it goes, but a checked box is a *claim*, not proof.
This skill verifies the claim: it walks every task in `tasks.md` and looks for real evidence
of completion — the code exists, the tests it promised exist and pass, the spec requirement
it maps to is actually satisfied, and no placeholder was left behind. It runs right after
implementation so gaps surface while the work is fresh, **before** the change is committed
and assumed done.

Analysis-only: it reports gaps, it never edits code or `tasks.md`. Fixing is the
implementer's call — this skill's job is to tell the truth about what is actually finished.

## Procedure

1. **Locate the artifacts.** Run `.specify/scripts/bash/check-prerequisites.sh --json --paths-only`
   to get `FEATURE_DIR`, `FEATURE_SPEC`, `IMPL_PLAN`, `TASKS`. If `TASKS` is missing, report
   there is nothing to review (implementation may not have generated tasks) and stop.

2. **Enumerate tasks.** Parse `tasks.md` into `{id, description, checkbox-state, referenced
   files/tests}`. Note which are marked done (`[x]`) vs open (`[ ]`).

3. **Verify each task against evidence — one at a time.** A checkbox is not evidence. For
   each task, confirm:
   - **Artifact exists** — the file(s)/symbol(s) the task describes are actually present in
     the working tree, not merely planned.
   - **Tests are real and green** — any test the task promised exists and passes. Run
     `/project-verify` (or the task's specific test) rather than trusting the box; test/security
     failures are blocking, lint is advisory.
   - **No stub left** — no `TODO`/`FIXME`/`pass`/`NotImplemented`/placeholder sitting where
     the task required real behavior.
   - **Requirement satisfied** — the spec requirement (FR-*) or acceptance scenario the task
     maps to is genuinely met, not just touched.

   Where there are many independent tasks, **fan the per-task verifications out in parallel**
   (one subagent per task or per cluster) and aggregate. The checks are independent, so this
   is faster and keeps each verdict isolated from the others.

4. **Cross-check coverage** between `spec.md` and `tasks.md`:
   - **Orphan requirements** — any FR-*/acceptance scenario with no implementing task.
   - **Orphan tasks** — any task that maps to no requirement (possible scope creep).

5. **Classify and report.** Give every task one of: **DONE** (verified), **INCOMPLETE**
   (marked done but evidence missing), **SKIPPED** (still open), or **UNVERIFIABLE** (needs a
   human/manual check — e.g. a live external dependency). Then state the summary verdict.

## Output template

ALWAYS use this structure so the gap between claimed and actual is unmistakable:

```text
## speckit-implement review — <FEATURE_DIR name>
**Verdict:** <ALL VERIFIED | GAPS FOUND (<n> incomplete, <m> skipped)>

| Task | Claimed | Verified | Evidence / Gap |
|------|---------|----------|----------------|
| T001 | [x] | ✅ DONE         | <file + passing test> |
| T0xx | [x] | ❌ INCOMPLETE   | <what's missing> |
| T0yy | [ ] | ⏭️ SKIPPED      | <not implemented> |

**Coverage gaps:**
- Orphan requirements (no task): <FR-… or "none">
- Orphan tasks (no requirement): <T… or "none">

**Punch list (finish before this is done):**
1. <task id> — <concrete fix>
```

## Notes

- **Evidence over checkboxes** is the entire point. If a task can only be confirmed by its
  checkbox, it is `UNVERIFIABLE`, not `DONE` — say so plainly rather than rubber-stamp it.
- **Analysis-only**, which is what makes it safe to auto-run: it never edits code or
  re-checks boxes. It produces the punch list; the implementer (or a follow-up
  `/speckit-implement`) acts on it.
- **Runs as an `after_implement` hook** (`.specify/extensions.yml`) so it fires the moment
  implementation finishes and before the auto-commit hook — gaps are cheapest to fix before
  the work is committed. It also runs standalone any time to re-audit.
- Complements `/project-verify` (deterministic lint/test/scan) and `speckit-analyze` (artifact
  consistency): this skill is specifically about **did we actually finish every task**.

## Sub-agent dispatch

When ≥3 independent task groups need auditing, dispatch one sub-agent per group to verify completion, then merge;
below that, audit inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or `parallel_agent.py` /
inline on other assistants. Dispatched sub-agents execute their task directly and do not re-dispatch.
