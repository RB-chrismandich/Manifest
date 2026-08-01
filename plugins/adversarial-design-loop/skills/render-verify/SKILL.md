---
name: render-verify
description: This skill should be used when the user asks to "verify the renders", "capture faithful screenshots of the screens", "run the render gate", "the fonts look wrong in the captures", "check chord clearance", or when a design loop needs its mechanical gates run before a review round or a ship. Renders exported HTML with hard-failing font/frame assertions and pixel-scans every ink color against the project's geometric limits.
version: 0.1.0
---

# Faithful rendering and pixel-forensic verification

The generator's own thumbnails are never authoritative — thumbnailers
mis-render (the source pass caught radial-gradient masks rendered wrongly).
The artifact of record is the **exported HTML** plus a **scripted,
assertion-gated screenshot** of that HTML. Every screen must pass this gate
before a review round judges it and before anything ships.

## The two mechanical gates

1. **Fonts-ready capture.** Before screenshotting, the script loads every
   declared webfont weight, awaits `document.fonts.ready`, and hard-fails
   if any weight did not load. A recurring "wrong font" defect in the
   source pass turned out to be a webfont load race, not a design bug —
   capturing without this assertion ships fallback-font screenshots that
   waste whole review rounds. The script also asserts the screen container
   is exactly the declared frame size.
2. **Ink scan against geometric limits.** After capture, the script scans
   the PNG per distinct ink color and reports each ink's pixel count,
   maximum radial reach from center, and maximum x/y extent — mechanically
   checking that no text or rim ink crosses the display's clearance limits
   (chord clearance on round displays; safe margins on rectangular ones).

## Running the gate

Use the project's pinned copy at `<artifact-dir>/tools/render_and_scan.py`,
placed there by `loop-scaffold`. This path is PROJECT-relative and correct as
written — run the command from `<artifact-dir>`. It is deliberately not the
plugin's own copy, which lives at
`${CLAUDE_PLUGIN_ROOT}/skills/render-verify/scripts/render_and_scan.py` and is
the source the scaffold copies from. Dependencies: Python 3.11+, `playwright`
(with Chromium installed), and `Pillow`.

```bash
cd <artifact-dir>
python3 tools/render_and_scan.py designs/<screen>.html designs/<screen>.png \
  --frame 360x360 --scale 2 \
  --font-family "Space Grotesk" --font-weights 400,700 \
  --radius-limit 171
```

- `--frame` — expected container size; capture aborts on mismatch.
- `--font-family` / `--font-weights` — the assertion set; omit only for
  system-font projects.
- `--radius-limit` — optional hard limit in frame pixels; any ink whose
  `r_max` exceeds it fails the gate (exit 1). For text-tier clearance use
  the project's text limit rather than the rim radius.
- `--bg` — background hex to exclude from the scan (default: sampled from
  the corner pixel).
- `--scan-only` — re-scan an existing PNG without re-rendering.

Interpret the output table (`hex / n / r_max / x_max / y_max`) against
TOKENS.md: every ink should be attributable to a token role, and every
`r_max` should sit inside the limit its role allows. An unattributable ink
is a finding (the generator introduced a value outside the design system).

## Rules

- **A failed gate is blocking.** No review round runs, and nothing ships,
  on a capture that failed a font, frame, or limit assertion.
- **Captures are deterministic artifacts.** Commit HTML and PNG together;
  re-render after every HTML edit — a stale PNG beside edited HTML is a
  cross-file staleness defect.
- **Prose rules become flags.** When a review round rules a new geometric
  constraint ("no text ink past r=152 at its own vertical offset"), encode
  it as a scan invocation in the project's verify recipe the same round —
  a gate nobody can run is a gate that quietly stops running.
- **The project pins its copy.** The gate lives in the project's `tools/`,
  versioned with the artifacts it judges; plugin updates must not silently
  change a project's gate. Diff and adopt updates deliberately.

## Additional resources

- **`${CLAUDE_PLUGIN_ROOT}/skills/render-verify/scripts/render_and_scan.py`** —
  the generalized gate (source of the project-pinned copy). `--help` documents
  all flags.
