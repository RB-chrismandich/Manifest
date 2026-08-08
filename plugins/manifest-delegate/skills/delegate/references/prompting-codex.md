# Prompting Codex

<!-- checklist: output contract (fenced JSON envelope requirement) |
     constraint framing (sandbox/approval mode, scope boundaries) |
     style/effort conventions (auto tier, terse task framing) -->

Codex defaults to `model_tier: auto` (`config/backends.json`) — do not
hardcode a specific model in the prompt; let the tier resolve.

## Composing the prompt

- State the task as a single, self-contained objective. Codex has no
  memory of this conversation unless you are resuming a session
  (`--resume` / `--resume-last`); a fresh invocation gets zero prior
  context, so restate every file path and constraint it needs.
- End every prompt with the envelope instruction: emit exactly one fenced
  ` ```json ` block as the last thing in the response, matching the
  `result-envelope.md` field set. Codex will otherwise return prose only,
  and `normalize_envelope()` will mark that a `failure`.
- Name the read-only vs write boundary explicitly in the prompt body even
  though the sandbox args (`--sandbox`) already enforce it — Codex should
  know why it can't touch disk, not just discover the rejection.
- Prefer imperative, scoped instructions ("edit X to do Y") over open
  framing ("look into X") — Codex's auto tier optimizes for a bounded
  task, not an exploratory one.
- If delegating a review rather than a task, say so explicitly and ask for
  findings in `follow_ups`, not inline commentary outside the envelope.
