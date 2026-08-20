# Prompting Cursor (cursor-agent)

<!-- checklist: output contract (fenced JSON envelope requirement) |
     constraint framing (sandbox + plan-mode read-only vs write) |
     style/effort conventions (flash default tier, repo-context bias) -->

Cursor defaults to `model_tier: flash` (`config/backends.json`), invoked as
`cursor-agent -p --output-format json` with the prompt piped on stdin.
The JSON envelope the CLI itself emits carries `result` (the reply text)
and `session_id` (the resume handle); `delegate.py` reads both, so the
prompt only has to produce the *inner* result envelope.

## Composing the prompt

- Cursor reasons from repository context by default and will happily open
  files you did not name. Name the boundary explicitly ("only files under
  `src/api/`") when the task is scoped, or it will widen on its own.
- Read-only runs launch as `--sandbox enabled --mode plan`; write runs drop
  only the mode (`--sandbox enabled`). Say which one applies in the prompt —
  plan mode still *proposes* edits, so a read-only run that is not told so
  tends to answer with a patch plan the caller must then discard.
- Close with the envelope instruction: one fenced ```json block, last in the
  output, matching `result-envelope.md`'s required fields. Cursor's default
  reply is prose with inline code, so state the requirement explicitly.
- Keep tasks single-shot at the flash tier; split staged work into separate
  `task` calls (optionally `--resume-last`) rather than one long prompt.

- Every invocation carries `--trust`: `cursor-agent` refuses to run in a
  directory it has not been trusted in, and a non-interactive dispatcher
  cannot answer that prompt. It answers the trust gate only — the run is
  still bounded by `--sandbox enabled` (and by plan mode when read-only),
  and the permission-dropping flags (`--yolo`, `--force`) are never used.

## Resume and failure modes

- Resume passes `--resume {session_ref}` with the captured `session_id`;
  the prior turn's context is retained, so add only what is new.
- Quota exhaustion is not an auth failure: the CLI exits 0 and prints a
  plain-text `ActionRequiredError: You've hit your usage limit` line instead
  of JSON. That surfaces as a malformed envelope, not a readiness failure —
  re-run with `--model` naming a tier the account still has budget for.
