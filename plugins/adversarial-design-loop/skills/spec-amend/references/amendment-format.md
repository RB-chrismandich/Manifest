# Amendment formats — verbatim worked examples

All excerpts are verbatim from the source pass (Lumient One,
`.stitch/SPEC-AMENDMENTS.md` and commit history).

## A complete amendment entry

Amendment #7 — the shortest clean instance of the full shape. Note that the
gap is argued from the spec's own text, and the recommended change is the
exact edit, ready to land:

```markdown
## 7. Menu content line — remove "factory reset" row, §7 (cross-note §6.1)

**What the spec says:** §7's Menu content line lists "face selection,
timezone, 12/24 h, night mode, about, factory reset" as menu rows.

**The contradiction (found round 15, ux lens):** §6.1 and firmware spec
§9/§6.6 define factory reset **exclusively** as the outcome of one
continuous press held past the long threshold — "Release to cancel" only
makes sense while a press is already in progress. A menu row is selected by
a discrete press-and-release, which is over before the row's action could
begin; a "Factory reset" row therefore advertises a press-to-erase input
the interaction model does not support (the "OK button implies an input
that doesn't exist" failure §6 warns about).

**Recommended spec change:** drop "factory reset" from §7's Menu content
line, leaving the §6.1 long-hold ladder as the sole, unambiguous reset
path (this matches firmware spec §9, which never mentions a menu path).
If a discoverable menu path is later wanted, it must be a distinct
instructional screen ("Hold the dial to reset"), designed and reviewed as
its own §7 row — not a direct jump into the hold-gated FactoryResetConfirm.

**Source:** `DECISIONS.md` round 15; `prompts/menu.md` (now five items).
```

## The status note (adopted vs landed, and gated landing order)

A dedicated closing section tracks landing centrally — including
dependency-gated ordering:

```markdown
## Amendment status note (rounds 16–17)

All eight amendments are now **landed** in the UI spec. Round 16 landed
amendment 7 (§7 Menu content line, edited inline) and amendment 8 (§5.2
light-ring sector budget, edited inline). Round 17 landed the two the
round-16 adoption block had omitted: amendment 1 (§3.4 night-palette
carve-out, inline note) and amendment 5 (§5 budget scoping, inline note).
The spec preamble's "Adopted design-pass amendments" block now enumerates
all eight, so no adopted change exists only in this side file.

**Rounds 19–20 add three, and none is landed.** Amendment 9 and 10 came out of
designing the four deferred system screens; amendment 11 came out of round
20's hardware review of them. All three are recommended rather than adopted...

**Land them in this order, and note 9 is gated:** 11 first (it is a pure
addition with no dependency), then 10 (wording), then 9 — which must not land
until firmware confirms the stage model AND supplies a failure/timeout signal...
```

## The landing commit

One atomic batch, each amendment enumerated with its target section, the
artifact tree committed alongside so the spec's back-pointers resolve:

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

## How landed edits look in the spec

- In-place rewrites: the §7 Menu table row simply drops "factory reset" and
  gains a parenthetical — *"(Amended in the Stitch design pass: 'factory
  reset' removed from this list … Rationale: `.stitch/SPEC-AMENDMENTS.md`
  §7.)"*
- Inline blockquotes beside the content they correct: *"Amendment 1
  (adopted): night-palette carve-out."* directly after the paragraph it
  amends.
- A preamble block enumerating the batch, so a reader entering at the top
  knows the spec has caught up with the design pass.
- Schema-only amendments (new token names) land as plain schema entries,
  adopted "by reference" via the preamble block only — no blockquote noise
  where no prose needed justifying.
