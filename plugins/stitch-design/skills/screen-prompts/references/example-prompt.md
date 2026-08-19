# Worked example — a complete colorless screen prompt

Verbatim from the source pass (Lumient One, `prompts/adjust-brightness.md`):
the shortest complete instance of the shared template. Annotations follow.

```markdown
# Stitch prompt — adjust-brightness

A single mobile screen on a solid black canvas. Centered on that canvas is one
perfect circle, edge to edge — this circle is the entire round display; every
piece of content lives inside it, nothing outside its edge, nothing anchored
to a canvas corner. This is a momentary "adjusting a single value" screen,
shown only while the user is actively turning a physical dial.

Composition, centre-out, deliberately minimal — no extra chrome beyond what is
listed:

- **A thin arc running around the very inside edge of the circle's rim**,
  spanning the full circumference as a track, with a continuous portion of
  that track — starting from one fixed point and sweeping clockwise — shown
  as a distinctly filled/lit arc, representing a single quantity filled from
  0% to 100%. In this composition, show the filled portion covering roughly
  two-thirds of the full ring, so the fill-vs-track distinction is clearly
  evaluable.
- **Dead center of the circle**: one large, dominant numeric value with a
  percent sign (e.g. a two-digit number followed by "%"), sized as the single
  biggest element on the whole screen.
- **Directly below that centered value**, a short single-word label in
  noticeably smaller text than the value above it, identifying what this
  value is (a brightness-style label).

Nothing else appears on this screen — no icons, no secondary text, no list,
no additional marks. The composition should feel like a single dial reading:
one ring showing a fill proportion, one big number, one small label beneath
it, all centered. No photographic or image content. Do not specify colors or
font names — this is a structural/layout-only wireframe; a separate design
system supplies color and typography.
```

## What to notice

- **Paragraph 1 is the frame contract**, shared near-verbatim by all 14
  prompts in the source pass, followed by one sentence of state semantics
  ("momentary... shown only while..."). The generator is told *when* the
  screen exists, not just what is on it.
- **Fill states are made evaluable.** "Roughly two-thirds" is not a design
  value — it is chosen so the fill-vs-track distinction can be judged in the
  render. Prompts stage the screen for review.
- **Dominance, not points.** "The single biggest element on the whole
  screen" and "noticeably smaller" replace font sizes; the tokens decide the
  numbers later.
- **The exclusion block does double duty**: it bans leftover chrome and
  hands the reviewer a testable claim ("no icons, no secondary text") to
  check the render against.
- **The closing boilerplate is verbatim across every prompt.** Treat it as a
  fixed string; a paraphrase invites the generator to negotiate.
- Other prompts in the source pass restate screen-relevant anti-pattern bans
  locally ("No icons, no chevrons, no toggle switches, no checkboxes, no
  drag handles, no full-circumference scrollbar...") — the design system's
  §7 list, repeated where the temptation will occur.
