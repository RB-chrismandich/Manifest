# Process contract — phase entry/exit criteria and conventions

Provenance: this process was extracted from a real 20-round design pass (the
Lumient One face/system-screens POC, 2026-07). Verbatim excerpts from that
pass appear as worked examples throughout this plugin's references.

## Phase contracts

### Phase 0 — spec first

- **Entry**: a request to design screens.
- **Exit**: an upstream spec exists that owns the runtime frame (e.g. a
  360×360 round face), the token *schema* (names and namespaces, not values),
  and the screen list. The design pass will fill the schema's values and
  visually resolve the screens; it will not invent requirements.

### Phase 1 — scaffold (`loop-scaffold` skill)

- **Exit**: artifact directory exists with all six artifact types plus
  `prompts/`, `designs/`, `tools/`; each template's placeholders are filled
  with the project's frame, fonts, generator, lens roster, and spec path.

### Phase 2 — design system

- **Exit**: DESIGN.md states every visual rule in prose with rationale;
  TOKENS.md holds the exact values plus proof tables (contrast ratios,
  spectrum constraints, radius conversions). The generator has a design
  system asset built from DESIGN.md, applied project-wide. Authority order
  is declared: spec, then TOKENS.md, then DESIGN.md prose, then renders.
  TOKENS.md and the renders are ground truth; DESIGN.md must track them.

### Phase 3 — prompts (`screen-prompts` skill)

- **Exit**: one prompt file per screen, all passing the colorless checklist
  (no hex, no color names, no font names or weights; geometry and relative
  emphasis only).

### Phase 4 — generate, tracked by ID

- **Exit**: every screen has a metadata.json entry with its generator screen
  ID (or `localOnly: true` for hand-authored screens), dimensions, and — for
  any revision — a `supersedes` field naming the replaced ID and a `note`
  saying why. A screen with no entry does not exist.

### Phase 5 — render-verify (`render-verify` skill)

- **Exit**: every screen has an exported HTML file and a faithful PNG
  captured by the project's pinned copy of the render script, with the
  fonts-ready assertion and frame assertion passing and the ink scan within
  the project's geometric limits.

### Phase 6 — review rounds (`review-round` skill)

- **Exit (consensus gate)**: a round in which every lens in the roster
  returns APPROVE and zero blocking findings survive the skeptic. Partial
  approval is not exit; "approved with one small blocker" is not a state.

### Phase 7 — spec amendments (`spec-amend` skill)

- **Exit**: every amendment is either landed in the upstream spec or
  explicitly gated (with the gate named) in the amendments file's status
  note. No adopted change exists only in the side file.

### Phase 8 — production rounds

- **Exit**: deferred scope shipped with mechanical gates passing, an honest
  commit message, and a DECISIONS.md entry recording that the screens have
  not faced the panel. Schedule the panel round; until it runs, the screens
  carry review debt.

## The consensus gate, precisely

A review round closes the loop only when all of the following hold:

1. Every lens in the roster returned **APPROVE** this round (not a carryover
   from an earlier round).
2. Every BLOCKING finding filed this round was either **REFUTED** by the
   skeptic or fixed, re-rendered, and re-verified by the filing lens within
   the round.
3. Each lens's report names what it independently re-derived — a round of
   four rubber stamps does not close the loop. A closing round should look
   like: each reviewer re-measured the load-bearing numbers rather than
   trusting the history.

## Commit conventions

Two commit shapes, taken verbatim (trailers trimmed) from the source pass.

**Amendment-landing commit** — lands the batch upstream and the artifact
tree in one atomic change, enumerating each amendment and its target
section:

```text
Adopt all 8 Stitch design-pass amendments into UI spec

Land the design-pass amendments from .stitch/SPEC-AMENDMENTS.md as
normative content in the UI design spec:

- §3.4 night-palette carve-out for the light-state ring (amendment 1)
- §5 damage budget scoped to the face renderer only (amendment 5)
- §7 Menu: factory reset removed; long-hold ladder is sole reset path
  (amendment 7)
- §5.2 light-state ring reclassified from "small, rare" to
  sector-budgeted at ≤ one 30° sector per tick, worst tick ≈ 51 KB
  (amendment 8)
- Header note adopting the remaining schema amendments (cct.warm/cool,
  radius.numeral, hand_*_tail, §13 type resolution) by reference

Also commit the .stitch/ design-pass artifacts the spec now points to.
```

**Production-round commit** — ships deferred scope and says outright what
scrutiny it did and did not receive. The load-bearing sentence is mandatory
in this shape:

```text
Ship 4 deferred system screens + light-ring verification variant

Closes the scope deferred at round 9 of the Stitch design pass: [...]

Screens passed the mandatory mechanical gates (chord-clearance scan,
fonts-ready capture) but not an adversarial panel — this was a production
round, not a review round.

Also closes two cheap advisories left standing at round 18 and syncs
DESIGN.md, TOKENS.md, DECISIONS.md, SPEC-AMENDMENTS.md, and metadata.json
with the shipped state.
```

Commit cadence: the loop iterates live in the working tree; git checkpoints
are few and batched (the source pass committed twice across 20 rounds), each
one leaving every governance file synced with the shipped state.

## Why each hard rule exists

- **Spec first** — prompts that quietly absorb requirement decisions make
  the spec unfalsifiable; nobody can later tell design intent from drift.
- **Colors/fonts only in the design system** — per-screen prompts that name
  colors let the generator drift the palette screen by screen; centralizing
  values makes drift structurally impossible.
- **Correction, not rewrite** — a decision log that silently rewrites itself
  destroys the evidence needed to audit *why* the current state is trusted.
  The source pass treated a withdrawn technical claim as worth recording
  precisely so it would not be repeated.
- **Round numbers as the shared clock** — dates and ticket IDs vary by tool;
  a round number lets one decision be traced through every artifact.
- **Supersede, never silently replace** — regeneration without lineage makes
  it impossible to know whether a fix survived the regeneration.
- **Prose rules → executable gates** — the source pass enforced two rulings
  "by eye" for five rounds before scripting them; both had silently stopped
  being checked. Hence: a ruling is durable when a script enforces it.
- **Adopted ≠ landed** — a "recommended" note in a side file is not an
  accepted spec change; treating it as one lets the spec and design diverge
  while both believe they agree.
- **Cross-file audit** — the source pass caught its own DESIGN.md
  documenting a geometry five rounds stale; the defect class is real and
  recurring, so it is every lens's jurisdiction.
- **Durable artifacts in git** — the generator's hosted state is neither
  diffable nor guaranteed to persist; the repo copy is the record.
