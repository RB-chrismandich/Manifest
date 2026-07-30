---
name: screen-prompts
description: This skill should be used when the user asks to "write the screen prompts", "author a Stitch prompt", "write a colorless wireframe prompt", "prompt the generator for a screen", or when a design loop reaches its prompt-authoring phase. Enforces one literal, geometry-only prompt file per screen with colors and fonts banned from prompt text.
version: 0.1.0
---

# Author colorless, geometry-only screen prompts

Write one prompt file per screen in `prompts/<screen-name>.md`. Prompts
describe pure composition and geometry; the design system asset supplies
every color and font. This split is what stops the generator drifting the
palette screen by screen — a prompt that names a color re-opens that door.

## The rules

1. **One file per screen**, named for the screen (`clock-day.md`,
   `adjust-brightness.md`). The file is the durable record of what the
   generator was asked; it is committed and never silently rewritten.
2. **Shared opening — the frame contract.** Every prompt begins with the
   same near-verbatim paragraph pinning the canvas and frame (for a round
   display: one perfect circle, edge to edge, nothing outside it, nothing
   anchored to a canvas corner), then one sentence saying what state the
   screen is and when it is shown.
3. **Centre-out composition, explicitly ordered.** List elements from the
   composition's anchor outward, each as a bullet: "Composition, centre-out,
   deliberately minimal — no extra chrome beyond what is listed."
4. **Geometry-only vocabulary.** Position by clock-face bearing ("roughly
   the 4:30 position") or fraction of the frame; size by relative dominance
   ("the single biggest element on the whole screen"); emphasis by relative
   treatment ("noticeably smaller", "clearly quieter"). Forbidden anywhere
   in the prompt: hex values, color names, font names, font weights,
   pixel-exact radii (the tokens own those).
5. **Close every prompt with the exclusion block.** State what does *not*
   appear ("Nothing else appears on this screen — no icons, no secondary
   text..."), restate the design system's anti-pattern bans this screen is
   most at risk of, then the standard closing boilerplate:

   > No photographic or image content. Do not specify colors or font names —
   > this is a structural/layout-only wireframe; a separate design system
   > supplies color and typography.

6. **Appendices grow, prompts do not rewrite.** When a later round changes a
   screen (a night variant, a stage model), append a dated section
   (`## Night variant (round N)`) cross-referencing DECISIONS.md or
   SPEC-AMENDMENTS.md by number. The original prompt text above stays
   untouched.
7. **Non-generated screens still get a file.** A verification variant or a
   hand-authored screen gets a prompt-shaped file documenting its diff from
   the parent screen, so `prompts/` stays a complete census.

## Checklist before generating

Run per prompt file:

- [ ] Opens with the shared frame contract; one-sentence state description.
- [ ] Every element positioned/sized in geometry-and-dominance vocabulary.
- [ ] Zero hex values, color names, font names, or weights (grep it:
      `grep -inE "#[0-9a-f]{3,6}|font|bold|serif" prompts/<name>.md` should
      match only the closing boilerplate's "font names").
- [ ] Exclusion block present; relevant anti-pattern bans restated.
- [ ] Standard closing boilerplate present verbatim.

## Additional resources

- **`references/example-prompt.md`** — a complete worked example (verbatim
  from the source pass) with the conventions annotated; use it as the
  filled reference while writing.
- **Template** — `../loop-scaffold/assets/templates/prompt.md.template` —
  the empty starting point to copy per screen.
