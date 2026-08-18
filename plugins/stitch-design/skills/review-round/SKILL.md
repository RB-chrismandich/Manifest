---
name: review-round
description: Run one adversarial design review round — parallel lens reviewers, skeptic-verified blockers, consensus gate.
version: 0.1.0
---

# Run one round — review (adversarial) or production (mechanical)

A round is the unit of scrutiny in the design loop. Review rounds put the
whole artifact set through the adversarial panel; production rounds ship
explicitly deferred scope through the mechanical gates only, and say so.
Every round gets the next integer in DECISIONS.md — round numbers are the
cross-reference key for every artifact in the tree.

## Review round

1. **Precondition.** Every screen under review passed the render gate this
   round (`render-verify` skill). Never spend the panel on stale captures.
2. **Dispatch the lenses in parallel** — one `design-lens-reviewer` agent
   per lens in the project's roster (default: feasibility, spec, ux, a11y),
   all in a single message so they run concurrently. Each dispatch prompt
   carries: the lens assignment and jurisdiction, absolute paths to the
   artifact directory and upstream spec, and the round number. Do not share
   one agent across lenses and do not pass one lens's findings to another —
   independence is the point.
3. **Collect verdicts.** Each lens returns APPROVE or BLOCK with findings
   (BLOCKING or ADVISORY) and the numbers it re-derived.
4. **Skeptic-verify every blocker.** For each BLOCKING finding, dispatch one
   `skeptic-verifier` agent (in parallel), given only the finding text and
   the artifact paths — never the filing lens's reasoning chain. Verdicts:
   REFUTED (with the ground, and where any real harm routes instead) or
   UPHELD (with the minimal fix and the sibling artifacts that must move
   with it).
5. **Apply upheld fixes.** Fix the artifacts, sync every named sibling
   (TOKENS.md, DESIGN.md, prompts, metadata.json move together), re-render
   (`render-verify`), and have the filing lens re-verify the specific
   finding. Advisories may be fixed, deferred, or declined — but log the
   choice.
6. **Log the round in DECISIONS.md** using the formats in
   `references/decisions-format.md`: the round header with per-lens
   outcomes, each blocker tagged REFUTED/UPHELD with the skeptic's ground,
   each ruling with its re-derived numbers, and any reversal as a
   correction naming what it withdraws. Never rewrite earlier rounds.
7. **Check the consensus gate.** The loop closes only on a round where every
   lens APPROVEs and zero upheld blockers remain — and each lens's report
   shows what it independently re-measured. Anything less means another
   round.

## Production round

For scope that was explicitly deferred in an earlier round (never for
scope that simply ran late):

1. Build the screens against the existing design system and tokens; give
   each a prompt file and a metadata.json entry like any other screen.
2. Run the mechanical gates — render gate, ink scan — as hard requirements.
3. **Declare the bar honestly.** The DECISIONS.md entry and the commit
   message must both state that the screens passed the mechanical gates but
   not an adversarial panel — this was a production round, not a review
   round. Never imply equivalent scrutiny.
4. **Record the debt.** The shipped screens carry review debt; schedule the
   panel round that pays it (the source pass ran its production screens
   through the full panel one round later, and the panel found real
   defects).

## Rules

- **Independence is structural.** Lenses run in parallel with no shared
  state; the skeptic sees the finding, not the reasoning that produced it.
- **A blocker is not accepted until it survives the skeptic**, and not
  closed until the fix is applied, siblings synced, re-rendered, and
  re-verified by the filing lens.
- **Corrections, not rewrites.** When a round overturns an earlier ruling,
  the log says so (`*Correction (round N):*`), keeping the withdrawn claim
  visible so it is not repeated.
- **Advisories left standing are tracked**, not forgotten — sweep them at
  production rounds ("closes two cheap advisories left standing at round
  18").

## Sub-agent dispatch

Every round dispatches: one `design-lens-reviewer` per lens, all in a single
message so they run concurrently, then one `skeptic-verifier` per BLOCKING
finding. That is the point of the round — independence is structural, so the
lenses must not be collapsed into one inline pass sharing context. Pick the
mechanism per the bundled `sub-agent-dispatch.md` selection rules: native
Task sub-agents on Claude, `[[skill:parallel-agent]]` or sequential re-reads
elsewhere.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`). Pass
the model explicitly; do not inherit the session's — a lens panel is wide, and
inheriting an Opus session multiplies its cost by the number of lenses.

## Additional resources

- **`references/decisions-format.md`** — verbatim worked examples of every
  DECISIONS.md entry shape: early rulings, corrections, panel headers,
  consensus rounds, REFUTED/UPHELD findings.
