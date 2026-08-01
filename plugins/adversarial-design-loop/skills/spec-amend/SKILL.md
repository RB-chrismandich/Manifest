---
name: spec-amend
description: Record design-pass findings that are upstream spec gaps, then land them as normative spec edits.
version: 0.1.0
---

# Spec amendments — record downstream, land upstream

When the design pass exposes a genuine hole in the upstream spec — a token
with no night-mode carve-out, two undocumented gradient colors, a menu row
the interaction model cannot support — the gap goes upstream as an
amendment. It is never patched silently into prompts or design files: a
spec that quietly diverges from its design cannot be audited by either
side.

## Distinguish first

- **Design defect**: the spec is right and the artifacts are wrong → fix
  the artifacts, log the ruling in DECISIONS.md. Not an amendment.
- **Spec gap**: the artifacts do the defensible thing and the spec is
  silent, wrong, or self-contradictory → amendment. The tell: the fix would
  edit the spec's own text.

## Record the amendment

Append a numbered entry to SPEC-AMENDMENTS.md (format is in
`../loop-scaffold/assets/templates/SPEC-AMENDMENTS.md.template`, resolved
relative to this skill's directory; a verbatim worked example is in
`references/amendment-format.md`):

```markdown
## N. <title> — §<target spec section>

**What the spec says:** ...
**The gap (found round N, <lens> lens):** ...
**Resolution already adopted:** ...
**Recommended spec change:** ...
**Source:** DECISIONS.md round N; <other artifacts>
```

Argue the gap from the spec's own text (quote it), give the resolution the
tree has already adopted, and write the recommended change ready to land —
the exact edit, not a direction.

## Adopt, then land — two states, tracked separately

- **Adopted**: the resolution is in force in the design tree (tokens,
  design system, prompts, renders all follow it). Adoption keeps the pass
  internally consistent while the spec lags.
- **Landed**: the upstream spec file itself is edited. An amendment is not
  done until landed — a "recommended" note in a side file is not an
  accepted spec change, and the loop's consensus gate should treat
  adopted-but-unlanded amendments as open items.

Maintain the **Amendment status note** section continuously: which
amendments landed and in what commit; which are adopted-not-landed and why;
and the landing order when amendments have dependencies ("11 first — pure
addition; then 10; then 9, gated on firmware supplying a failure signal").
A gated amendment must name its gate; it must not land early.

## Land the batch

Once the design pass stabilizes (typically at the consensus gate), land all
un-gated amendments as one batch:

1. **Edit in place, normatively.** Splice each amendment into the exact
   target section — rewrite the sentence, edit the table row, insert the
   blockquote beside the content it corrects. Do not append a changelog to
   the spec; the spec's prose itself becomes correct.
2. **Point back.** Each landed edit carries a rationale pointer to the
   amendments file ("Rationale: `<artifact-dir>/SPEC-AMENDMENTS.md` §N"),
   and the spec's preamble gains/updates an "Adopted design-pass
   amendments" block enumerating the batch. Schema-only amendments may land
   by reference in that block rather than as inline blockquotes.
3. **Commit atomically**, enumerating each amendment and its target section
   in the message (worked example in `references/amendment-format.md`).
   Land the artifact tree in the same commit if it is not yet committed —
   the spec must never point at files git does not have.
4. **Verify closure**: after landing, no adopted change exists only in the
   side file. Update the status note with the commit hash.

## Additional resources

- **`references/amendment-format.md`** — a complete verbatim amendment
  entry, the status-note shape, and the landing commit message from the
  source pass.
