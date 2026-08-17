# Prompting Antigravity (agy)

<!-- checklist: output contract (fenced JSON envelope requirement) |
     constraint framing (sandbox plan vs accept-edits mode) |
     style/effort conventions (flash default tier, single-shot framing) -->

Antigravity defaults to `model_tier: flash` (`config/backends.json`),
invoked via `agy --print <prompt>`. Known gotcha: print mode ignores piped
stdin, so `delegate.py` uses the bounded `argv` transport and passes the
prompt as the `--print` value. This is a dispatcher concern, not something
the prompt text needs to account for, but it means retries must re-supply
the full prompt rather than relying on a buffered stream.

## Composing the prompt

- Flash is the fast/cheap tier — keep the task narrowly scoped and
  single-shot. If the work naturally splits into stages, delegate them as
  separate `task` calls (optionally `--resume-last`) rather than one
  sprawling prompt; a smaller model executes a bounded instruction more
  reliably than an open-ended one.
- Still close with the envelope instruction: one fenced ```json block,
  last in the output, matching `result-envelope.md`'s required fields.
  Antigravity's conversational default is a plain-prose reply, so state
  the requirement explicitly rather than assuming it's implied.
- Name the read-only/write boundary in the prompt (`--sandbox --mode
  plan` vs `accept-edits`) — flash-tier runs are more likely to attempt a
  write "helpfully" if not told the run is read-only and why.
- Session resume uses `--conversation {session_ref}`, captured from
  `conversation_id:` in the prior output — do not ask Antigravity to
  restate context it already has when resuming; only add what's new.
