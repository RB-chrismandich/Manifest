# Result Envelope — Presentation Rules

<!-- checklist: output contract (envelope fields + failure semantics) |
     constraint framing (never fabricate, never re-derive from prose) |
     style/effort conventions (terse relay, no editorializing) -->

`delegate.py` mechanically extracts the last fenced JSON block from a
backend's stdout and normalizes it against `result-envelope.schema.json`.
This file governs how you — the dispatching skill or relaying agent —
present that envelope to the user. It does not change extraction; that is
Python's job (FR-002).

## The envelope

Required fields on every envelope: `backend`, `model`, `outcome`,
`attempted`, `changes`, `succeeded`, `failed`, `follow_ups`. `outcome` is
one of `success`, `partial`, `failure`. A `failure` outcome always carries
`error`; missing-field or unparsable output is normalized to `failure`
with `raw_output` preserved verbatim.

Task, review, and gate prompts also request `findings` as objects with string
`severity` and `text` fields. The list is the bounded handoff surface for
`--second-opinion`; use `[]` when there is no conclusion to cross-check.

## Presentation rules

- Relay `attempted`, `succeeded`, `failed`, and `follow_ups` as given —
  never rewrite, summarize away, or soften a `failed` entry.
- On `outcome: failure`, surface `error` first, then `raw_output` if the
  user needs to diagnose it. Do not guess at what the backend meant.
- Never synthesize a `changes` entry the envelope didn't report, even if
  you can see the diff yourself — the envelope is the backend's own
  account, not your observation.
- If `follow_ups` is non-empty, surface each item; do not silently drop
  ones that look redundant or out of scope.
- Do not append your own opinion of quality to a relayed envelope unless
  the user asked for a second opinion (`--second-opinion`), which is a
  separate, explicitly-labeled envelope, not a mutation of the first.
