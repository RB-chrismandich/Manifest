# Prompting Devin (devin)

<!-- checklist: output contract (fenced JSON envelope requirement) |
     constraint framing (permission-mode auto vs accept-edits, sandbox) |
     style/effort conventions (auto tier, no resume, bounded argv) -->

Devin defaults to `model_tier: auto` (`config/backends.json`) — the account's
own default model. `auto` is also the only tier that resolves: tier names are
looked up in `configs/claude/config/parallel_agent.yml`, which carries no
`model_tiers.devin` block (its catalog is login-gated), so any other `--model`
value is rejected before dispatch. Invocation is `devin -p <prompt>` with the
prompt passed as the `-p` value.

## Composing the prompt

- The transport is bounded `argv` (64 KiB), not stdin: an oversize prompt is
  rejected with an explicit error naming the limit, never truncated. For a
  large diff, narrow the scope (`--base`, a path subset) instead of trying to
  send everything.
- Read-only runs launch as `--permission-mode auto --sandbox`; write runs as
  `--permission-mode accept-edits --sandbox`. `auto` auto-approves only
  read-only tools, so a read-only run cannot silently edit — but say so in
  the prompt anyway, so the reply is findings rather than a half-applied plan.
- Close with the envelope instruction: one fenced ```json block, last in the
  output, matching `result-envelope.md`'s required fields.

## No resume — re-send context

- `resume` is `null` for this backend: the CLI has `-r <SESSION_ID>`, but a
  print-mode run emits no session id on stdout and leaves no entry for the
  directory in `devin list` (measured 2026-08-19 on an authenticated
  account), so there is nothing to capture. The dispatcher discloses that
  resume is unavailable and re-sends context (FR-015) — write follow-up
  prompts as self-contained restatements; do not refer to "the previous run".
- Readiness is login-gated and `devin auth status` **exits 0 even when
  logged out** — the readiness probe classifies it by reading the output
  ("Not logged in."), so trust the `state` column, not the exit code.
- Devin is opt-in: `services.yml` ships it disabled, so its readiness row
  reads `disabled_workspace` until enabled (`./bootstrap.sh --enable-devin`).
