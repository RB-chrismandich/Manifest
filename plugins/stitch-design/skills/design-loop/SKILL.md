---
name: design-loop
description: Use when kicking off or resuming a full adversarial, spec-first UI design pass — scaffolds artifacts, drives generation through review rounds until every lens approves, and routes spec gaps back upstream. Entry point orchestrating the design loop sibling skills end to end.
version: 0.1.0
---

# Adversarial Design Loop — orchestrator

Run a UI design pass as a disciplined loop: a spec that already exists is
visually resolved by a generator (Stitch or any other), verified by a real
render pipeline, reviewed by an adversarial multi-lens panel, and any spec
gaps the pass exposes are amended upstream — with every decision left as a
durable, auditable git artifact.

## Preconditions (phase 0 — spec first)

1. An upstream UI spec exists and owns the requirements: runtime frame,
   token schema, screen list. Confirm it exists — do not collect its path
   here; the `loop-scaffold` interview captures it. If there is no spec,
   stop and write one first — the generator is never used to invent
   requirements.
2. Confirm the generator is available (for Stitch: the `mcp__stitch__*` tools;
   any generator that exports real HTML works; screens can also be
   hand-authored against the tokens with no generator at all).
3. Note only whether the default lens roster (feasibility/spec/ux/a11y) is
   likely to fit — the `loop-scaffold` interview finalizes it.

## Phases

Execute in order; each phase's exit criteria gate the next. Detailed
entry/exit contracts: `references/process.md`.

1. **Scaffold** — invoke the `stitch-design:loop-scaffold` skill: create the artifact
   directory (default `.stitch/`) with DESIGN.md, TOKENS.md, DECISIONS.md,
   SPEC-AMENDMENTS.md, metadata.json, prompts/, designs/, tools/.
2. **Design system, hand-authored** — write DESIGN.md (mood, palette roles,
   type, components, layout, anti-patterns) and TOKENS.md (exact values,
   proof tables) before generating anything. Turn DESIGN.md into the
   generator's design-system asset and apply it to every screen. Exact
   colors and font names live only here — never in screen prompts.
3. **Screen prompts** — invoke the `stitch-design:screen-prompts` skill: one colorless,
   fontless, geometry-only prompt file per screen.
4. **Generate → edit → re-verify, tracked by ID** — generate each screen
   against the design system; revise in place through edit passes. Record
   every screen's generator ID in metadata.json, and every replacement as a
   `supersedes` chain entry with a note saying what it replaced and why.
   Never silently regenerate from scratch.
5. **Render and verify** — invoke the `stitch-design:render-verify` skill: the generator's own
   thumbnails are never authoritative; the artifact is exported HTML plus a
   scripted, fonts-ready-asserted capture, pixel-scanned against the
   project's geometric limits.
6. **Review rounds** — invoke the `stitch-design:review-round` skill repeatedly: parallel
   lens reviewers, skeptic-verified blockers, every ruling logged in
   DECISIONS.md. The loop exits only on the consensus gate: every lens
   APPROVE, zero upheld blockers.
7. **Spec amendments** — whenever a round exposes a genuine hole in the
   upstream spec, invoke the `stitch-design:spec-amend` skill: record it, adopt the
   resolution in the design system, and land the batch upstream once the
   pass stabilizes. Design-side fixes and spec-side gaps stay separate.
8. **Deferred scope → production rounds** — scope may be deferred
   explicitly, never rushed. Deferred screens ship later through a declared
   production round (`stitch-design:review-round` skill, production variant): mechanical
   gates only, and the commit message says outright that no adversarial
   panel ran.

## Hard rules (apply in every phase)

- **Spec first.** Gaps found downstream go upstream as amendments, never
  into ad-hoc prompt patches.
- **Colors and fonts live in the design system only.** Prompts are
  structural wireframes; the design system supplies the rest.
- **Correction, not rewrite.** Reversals are logged as corrections naming
  what was withdrawn and why; earlier text is never silently edited away.
- **Round numbers are the cross-reference key.** All artifacts cite each
  other by round ("round 15 ruling"), giving one shared clock.
- **Supersede, never silently replace.** Every regenerated screen points at
  what it replaced and why, in metadata.json.
- **Prose rules become executable gates.** A review ruling is not durable
  until a script enforces it; "a gate nobody can run is a gate that quietly
  stops running."
- **Adopted is not landed.** A spec amendment adopted in the design system
  is still open until edited into the upstream spec itself.
- **Cross-file agreement is audited, not assumed.** A correction applied in
  one artifact but not its siblings is a blocking defect.
- **Everything durable, in git.** Prompts, HTML, faithful PNGs, tokens,
  decisions, amendments, IDs, supersession history — committed, so any
  decision can be audited without re-querying the generator.

## Additional resources

- **`references/process.md`** — per-phase entry/exit contracts, the
  consensus gate, commit-message conventions with worked examples, and the
  rationale behind each hard rule.
