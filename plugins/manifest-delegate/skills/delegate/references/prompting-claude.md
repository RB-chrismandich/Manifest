# Prompting Claude

<!-- checklist: output contract (fenced JSON envelope requirement) |
     constraint framing (permission-mode plan vs acceptEdits) |
     style/effort conventions (sonnet default tier, delegated-not-nested) -->

Claude defaults to `model_tier: sonnet` (`config/backends.json`). This is
a *separate* Claude Code process, not a sub-agent of the current session —
treat it like any other backend: it starts cold, with no shared context.

## Composing the prompt

- Give it the full task in one shot: objective, exact file paths (always
  absolute — the child process's cwd is not guaranteed to match yours),
  and any prior findings it needs, since it cannot see this transcript.
- Close with the envelope instruction: the last thing in its output must
  be a single fenced ```json block matching `result-envelope.md`'s field
  set, or `normalize_envelope()` records the run as a `failure` even if
  the work succeeded.
- State the read-only/write boundary in the prompt itself. `--permission-
  mode plan` (read-only) vs `acceptEdits` (write) already constrains what
  it *can* do; tell it what it's *for*, so a read-only run reports
  findings instead of silently attempting edits it expects to be blocked.
- Avoid re-explaining Claude Code mechanics (hooks, skills, slash
  commands) — the child process already knows its own runtime. Spend the
  prompt budget on the task's specifics instead.
- For a second opinion, frame it as a critique of a specific prior
  envelope (pass `--of JOB_ID`), not a fresh attempt at the same task —
  ask it to agree, disagree, or flag gaps against what was reported.
