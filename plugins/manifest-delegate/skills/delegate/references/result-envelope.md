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

## Parent aggregation of multiple relays

When a parent explicitly requested multiple independent external results, it may
present a separate **Parent aggregation** after the individual relays. The
section may deduplicate findings only after validating them against the stated
input scope. Attribute every retained finding and conclusion to its `job_id` and
`backend`; preserve each original envelope verbatim and never edit it to fit the
aggregation.

- Keep failed, partial, malformed, unavailable, and missing-findings results
  visible with their per-envelope error or follow-up. They are not agreement,
  and they never make the aggregate a clean review.
- Record the revision or diff scope used by each job. If scopes differ, state
  that results are not directly comparable rather than claiming consensus.
- Report unresolved disagreement as unresolved. Text overlap, finding counts,
  and vote percentages are not correctness evidence.
- The parent, not a runner or backend, owns evidence validation, lifecycle
  decisions, and the separately labeled synthesis.
