# adversarial-design-loop

A Claude Code plugin that runs UI design passes as a disciplined,
auditable loop: **spec first, generator second, adversarial review always,
every decision a durable git artifact.**

Extracted from a real 20-round design pass (the Lumient One face/system
screens POC): the process survived contact with a 360×360 round display, a
generator whose thumbnails could not be trusted, four review lenses, a
skeptic role, and eight spec amendments — and this plugin codifies what
worked, generalized to any display shape, generator, and lens roster.

## The loop

1. **Spec first.** An upstream spec owns the requirements; the generator
   only resolves them visually. Gaps found later go upstream as
   amendments, never into ad-hoc prompt patches.
2. **Hand-authored design system.** DESIGN.md (rules + rationale) and
   TOKENS.md (exact values + proof tables) exist before any screen;
   colors and fonts live only there.
3. **Colorless screen prompts.** One geometry-only prompt file per screen;
   the design system supplies the rest, so the palette cannot drift
   screen by screen.
4. **Generate → edit → re-verify, tracked by ID.** Every revision records
   what it superseded and why, in metadata.json.
5. **Faithful render gate.** Generator thumbnails are never authoritative:
   exported HTML + a scripted capture with hard-failing font/frame
   assertions and a per-ink pixel scan against geometric limits.
6. **Adversarial review rounds.** Parallel lens reviewers
   (feasibility/spec/ux/a11y by default), every blocker independently
   skeptic-verified (REFUTED/UPHELD), all logged append-only in
   DECISIONS.md. The loop closes only at full-roster APPROVE with zero
   upheld blockers.
7. **Spec amendments, adopted then landed.** Recorded with the resolution
   already adopted, landed upstream as in-place normative edits in one
   enumerated batch.
8. **Production rounds, declared honestly.** Deferred scope ships through
   mechanical gates only — and the commit message says so outright.
9. **Everything in git.** Prompts, HTML, faithful PNGs, tokens, decisions,
   amendments, IDs, supersession history.

## Components

| Component | Name | Purpose |
|-----------|------|---------|
| Skill | `design-loop` | Orchestrates the full loop phase by phase |
| Skill | `loop-scaffold` | Creates the artifact tree from templates |
| Skill | `screen-prompts` | Colorless, geometry-only prompt authoring |
| Skill | `render-verify` | Faithful render gate + ink scan |
| Skill | `review-round` | One adversarial (or production) round |
| Skill | `spec-amend` | Amendment recording, adoption, landing |
| Agent | `design-lens-reviewer` | One lens of the panel, assigned at dispatch |
| Agent | `skeptic-verifier` | Refutes or upholds each blocking finding |
| Script | `render_and_scan.py` | Playwright capture + pixel-forensic scan |

## Installation

From this repository (registered as a directory marketplace):

```bash
claude plugin marketplace add /path/to/Manifest
claude plugin install adversarial-design-loop@manifest
```

Or for a one-off test session:

```bash
claude --plugin-dir /path/to/Manifest/plugins/adversarial-design-loop
```

## Prerequisites

- **Generator (optional):** the Stitch MCP server (`mcp__stitch__*` tools)
  is the reference generator; any generator that exports real HTML works,
  as does hand-authoring screens against the tokens.
- **Render gate:** Python 3.11+, `playwright` (with
  `playwright install chromium`) and `Pillow`.

## Quick start

```text
/adversarial-design-loop:design-loop
```

Point it at an existing UI spec. It will refuse to invent requirements —
that is the point.

## Provenance

Process reconstructed from the Lumient One design pass artifacts
(`.stitch/` — DECISIONS.md rounds 1–20, DESIGN.md, TOKENS.md,
SPEC-AMENDMENTS.md ×11, metadata.json, 14 prompts, render tooling) and the
two commits that landed that work. Verbatim excerpts from those artifacts
appear throughout the skills' `references/` as worked examples.
