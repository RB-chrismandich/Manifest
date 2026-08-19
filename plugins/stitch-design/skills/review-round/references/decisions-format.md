# DECISIONS.md entry formats — verbatim worked examples

All excerpts are verbatim from the source pass's DECISIONS.md (Lumient One,
rounds 1–20). Use these shapes; the discipline they encode is
correction-not-rewrite and evidence-over-recall.

## Ruling (any round)

A bold claim naming exactly what changed (with values), then the rationale
with the numbers that justify it:

```text
- **`hand.minute` recolored from `#C8D0D8` (identical to `face.tick_major`) to
  its own role, `#9AA5B2`/`#8A2E00` ("Dial Steel").** Round 1/2 gave the
  minute hand and the major tick marks the exact same hex — not a borderline
  ratio, a literal identity — which, combined with an identical radius (both
  0.80 R), pixel-merged the hand into a tick 12 times an hour. See "Numerals
  and face layout" below for the paired radius fix; the two together mean
  either alone would have resolved it.
```

## Correction (reversal that keeps the evidence)

Left in place beside the original claim, naming what is withdrawn, why, and
what stands instead:

```text
- **`face.tick` tuned from `#5B6572` (3.04:1) to `#626C79` (3.38:1).**
  *Correction (round 3):* this was originally justified as "RGB565 rounding at
  render time" pushing `#5B6572` below the 3:1 floor — re-checked, and that
  specific mechanism does not reproduce; ... Recorded here so the withdrawn
  technical claim isn't repeated.
```

Note the shape: the *color kept its change* because the simpler reason still
held — only the wrong justification was withdrawn. Corrections fix the
record, not necessarily the decision.

## Panel round header (multi-lens era)

States each lens's outcome up front, then the rulings:

```text
## Round 15 rulings — menu reset row, minute-hand clearance

Hardware and spec lenses approved this round; ux and a11y each upheld one
blocker. Rulings:

- **"Factory reset" is no longer a menu row.** The ux lens caught a real
  interaction contradiction that fourteen rounds missed: ...
- **`radius.hand.minute` 0.75 R → 0.72 R.** The a11y lens recomputed the
  worst case from the tokens and refuted this file's round-1/2 rationale: ...
```

## Consensus round (the gate that closes the loop)

Unanimity plus proof of independence — each lens's re-derivation named:

```text
## Round 18 — CONSENSUS

All four lenses approved with zero upheld blocking findings. Each reviewer
independently re-derived the load-bearing numbers rather than trusting the
history: hardware re-measured strokes, ring tiling, the hue marker's 210.2°
vs its displayed 210°, and the §5.2 arithmetic (≈51KB of 64KB with the ring
sector counted); spec verified all 17 color roles ×2 palettes, 6 radius
roles, 3 stroke tiers, 4 type roles, and every §7/§7.1/§10.2 content
contract, with all eight amendments landed in the spec itself; ux verified
the markup (focus is brightness-only at equal weight; the night ring
differs from day by color alone, matching Amendment 1); a11y recomputed
every contrast pair to two decimal places and confirmed blue=0 across every
pixel of the night render.
```

## Skeptic-verified blockers (REFUTED / UPHELD)

Each blocking finding carries its verdict tag, the skeptic's ground, and —
for refuted findings — where the real harm routes instead:

```text
## Round 20 — the round-19 screens through the panel

Round 19 shipped five artifacts without a review; this round put them through
the standard four lenses. **Hardware and a11y approved. Ux and spec each
blocked.** Three blocking findings, one refuted by a skeptic and two upheld —
and both upheld ones are defects in this project's own documentation, not in
the screens.

### Blocking findings

- **REFUTED — "Commissioning has no failure state, so a stalled pairing
  strands the user" (ux).** The strongest version of this argument is better
  than the one round 19 filed against itself: ... The skeptic upheld the harm
  and refuted the verdict: the gap was already found, named and routed
  (`SPEC-AMENDMENTS.md` §9, `prompts/commissioning.md`), and the remedy
  requires a firmware timeout and failure signal that exist nowhere ...
- **UPHELD — `DESIGN.md` §4 still documented `hand.minute` = 0.75 R (spec).**
  Round 15 moved it to 0.72 R ... `TOKENS.md` and every render were updated;
  this file was not, so for five rounds the readable rationale layer
  documented a geometry that would fail the exact collision it claims to fix.
```

## Format rules distilled

1. Round header: `## Round N — <topic>` (or `— CONSENSUS`). Rounds only
   append; numbering never resets or backfills.
2. Per-lens outcomes stated in the header paragraph before any ruling.
3. Every blocker in the log carries **REFUTED** or **UPHELD**, the skeptic's
   ground, and the routing of any real-but-refuted harm.
4. Every ruling embeds the values and measurements that justify it — a
   ruling without numbers is not auditable.
5. Reversals use `*Correction (round N):*` (inline) or
   `**Round N correction to ...**` (section-level) and never delete the
   text they correct. Sibling files (DESIGN.md, TOKENS.md) use the same
   marker when a round moves their content.
6. Cross-reference by round number, never by date.
