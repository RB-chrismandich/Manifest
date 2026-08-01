---
name: loop-scaffold
description: This skill should be used when the user asks to "scaffold the design loop", "set up the .stitch directory", "initialize the design-pass artifacts", "create the design loop tree", or starts an adversarial design pass in a repo that has no artifact directory yet. Creates the six governance artifacts, prompts/designs/tools directories, and the pinned render gate from templates.
version: 0.1.0
---

# Scaffold the design-loop artifact tree

Create the durable artifact directory that an adversarial design pass lives
in. Everything the loop produces — prompts, exported HTML, faithful PNGs,
tokens, decisions, amendments, screen IDs — belongs in this tree, in git.

## Interview first

Collect these before creating anything (ask only for what cannot be
inferred from the repo):

1. **Upstream spec path** — the spec must already exist; it owns the runtime
   frame, the token schema, and the screen list. If there is no spec, stop:
   write the spec first (the `design-loop` skill, phase 0). Do not scaffold
   a design pass for requirements that live nowhere.
2. **Project title** — a short human-readable name for the design pass,
   used as the H1 of every governance file and in metadata.json. Infer from
   the repo/product name if the user does not state one; confirm before
   writing it.
3. **Frame** — width×height of the screen container (e.g. `360x360`) and
   display shape (round displays add chord-clearance limits; rectangular
   ones add safe-margin limits). The frame radius used by TOKENS.md is
   derived, not asked: half the frame's shorter dimension (360x360 → 180).
4. **Typography** — webfont family and the weights screens will use (the
   render gate asserts these load before every capture).
5. **Generator** — `stitch` (via the `mcp__stitch__*` tools), another
   HTML-exporting generator, or `none` for hand-authored screens.
6. **Lens roster** — default `feasibility, spec, ux, a11y`; swap lenses that
   do not fit the project (a pure-web project may not need feasibility).
7. **Artifact directory name** — default `.stitch/` when the generator is
   Stitch; otherwise `.design-loop/`.

## Create the tree

```text
<artifact-dir>/
├── DESIGN.md            # design system prose: rules + rationale
├── TOKENS.md            # exact values + proof tables; normative over DESIGN.md
├── DECISIONS.md         # append-only round log
├── SPEC-AMENDMENTS.md   # upstream gaps: adopted vs landed
├── metadata.json        # screen registry: IDs, supersedes chains
├── prompts/             # one colorless prompt file per screen
├── designs/             # exported HTML + faithful PNG per screen
└── tools/
    └── render_and_scan.py   # the project's pinned render gate
```

Steps:

1. Copy each template from `assets/templates/` in this skill's directory to
   its target name (`DESIGN.md.template` → `DESIGN.md`, etc.), then replace
   every `{{PLACEHOLDER}}` with the interviewed values — deriving
   `{{FRAME_RADIUS}}` from the frame, and confirming an inferred
   `{{PROJECT_TITLE}}` if the user did not state one. Delete any template
   guidance comments that do not apply.
2. Copy the render gate from the sibling skill —
   `${CLAUDE_PLUGIN_ROOT}/skills/render-verify/scripts/render_and_scan.py` —
   into `<artifact-dir>/tools/`. Use the variable, not a relative path: a
   shell command runs with the cwd set to the user's project, not to this
   skill's directory, so `../render-verify/...` resolves against the wrong
   root and the copy silently lands nowhere or fails. The project owns and
   pins its copy: gates must not change under a project because a plugin
   updated. Record the copy's provenance in the Round 0 entry — fill
   `{{PLUGIN_VERSION}}` from the plugin's `.claude-plugin/plugin.json`.
3. Initialize `metadata.json` from `metadata.template.json` with an empty
   `screens` map.
4. Open DECISIONS.md with a "Round 0 — scaffold" entry recording the
   interviewed parameters, the lens roster, and the spec path, so round
   numbering starts with an auditable anchor.
5. Commit nothing yet — the first commit lands with real content, but stage
   the tree so nothing is invisible to git.

## Rules the scaffold encodes

- Exact colors and font names will live only in DESIGN.md/TOKENS.md — the
  prompt template's closing boilerplate forbids them per screen.
- TOKENS.md is normative over DESIGN.md prose; both files' preambles say so.
- DECISIONS.md is append-only: corrections are logged, never rewritten in.
- SPEC-AMENDMENTS.md tracks **adopted** (in the design system) and
  **landed** (edited into the upstream spec) as separate states.

## Additional resources

- **`assets/templates/`** — DESIGN.md.template, TOKENS.md.template,
  DECISIONS.md.template, SPEC-AMENDMENTS.md.template,
  metadata.template.json, prompt.md.template. Copy and fill; the templates
  carry their own inline guidance.
