# Skill Front-Matter Efficiency Pass — Design

**Date**: 2026-07-05
**Status**: Approved (design); ready for implementation planning
**Author**: Claude Code (brainstorming skill)
**Branch**: `feat/skill-frontmatter-efficiency`

---

## Problem

Claude Code auto-loads **every** skill's YAML `description` into agent context at the
start of **every** session. It is the always-loaded triggering text that decides
whether a skill fires. The CI gate `tests/bats/context_budget.bats` counts the raw
bytes of each skill's front-matter (everything between the two `---` markers) and
enforces a hard cap.

Measured current state (`.skillshare/skills/*/SKILL.md`, 88 skills):

| Metric | Value |
|---|---|
| Total front-matter | **21,656 bytes** |
| Budget cap (`context_budget.bats`) | 22,800 bytes |
| Headroom | ~1,144 bytes |
| Description styles | 49 inline · 31 literal `\|` · 8 folded `>` |
| Skills over the ~290-char norm | 18 |
| Heaviest | `pr-smoke` (359) |

Two problems: (1) style is inconsistent, and literal/folded block scalars pay a
byte tax the always-loaded budget charges for; (2) ~18 descriptions are verbose
relative to their triggering need. The set is already fairly lean — this is an
optimization and consistency pass, **not** a rescue.

## Goal

Make **all** 88 skills' front-matter efficient — minimum bytes for the CI gate and
minimum tokens in loaded context — **without weakening any skill's triggering**.

Non-goals: renaming skills, editing skill bodies, changing the naming taxonomy.
Descriptions (and, for D1/D2, the budget gate + one doc) only.

## Key technical insight

There are two distinct notions of "efficient front-matter" and they do not move
together:

- **Gate bytes** — `context_budget.bats` counts *raw bytes* between `---` markers.
  A `description: |` (literal) or `description: >` (folded) block pays a hidden
  tax: two-space indentation on every wrapped line plus the block wrapper.
- **Context tokens** — Claude Code loads the *parsed* description value; YAML
  indentation is stripped. Inline single-line is the fewest bytes for the gate
  and carries no wrapper tax.

This splits the work into two levers with very different risk profiles.

## Approach — two levers

### Lever A — Formatting normalization (mechanical, low risk)

Convert all 31 literal `|` and 8 folded `>` descriptions to **inline single-line**.

- **Folded `>` → inline**: parsed value is byte-identical (folded already collapses
  newlines to spaces). Zero semantic change.
- **Literal `|` → inline**: parsed value changes wrapped-prose newlines to spaces.
  **Verified safe**: all 31 literal blocks are wrapped single-prose — zero blank
  lines, zero list markers (`- `/`* `) — so newline→space is benign and in fact
  repairs mid-sentence embedded newlines. Each conversion is confirmed by a
  trigger-phrase diff (see Verification).

**CI-safety of long inline lines — verified**: a 281-char inline description
(`ci-audit-triggers`) already passes CI. `yamllint` does not lint `.md` files
(pre-commit `yamllint` hook runs on YAML only), and `markdownlint` MD013
(line_length 120) does not flag front-matter scalar lines. Inline is therefore
CI-safe at any length.

**YAML colon-safety — required**: a plain (unquoted) YAML scalar cannot contain
`: ` (colon-space). 11 block-style descriptions contain a colon-space and would
break parsing if inlined unquoted:

```
ai-code-audit, git-commit, graphify, issue-dev-auto, issue-triage,
learning-capture, metrics-report, performance-check, pr-monitor,
pr-smoke, repo-clean
```

House rule: inline **unquoted** by default; **double-quote** the description when
its text contains `: `, or begins with a YAML indicator (`- ? : [ ] { } # & * ! | > ' " % @ \``).
Escape any embedded `"` as `\"`. (Double-quoted inline is fewer bytes than keeping
a folded block; folded `>-` is an acceptable fallback if quoting is awkward.)

### Lever B — Content trim (eval-guarded, real risk)

Shorten the ~18 descriptions whose **total front-matter exceeds the ~290-byte
norm** (the same metric `context_budget.bats` counts; skill names are short ASCII
tokens, so front-matter bytes track description length closely) toward ~275,
preserving every distinct trigger token and "use-when" cue.

**Non-trimmable content** (never removed by a trim):
- Security-critical keywords (e.g. `auth`, `crypto`, `secrets`, `injection`,
  `pull_request_target`) that drive security-skill triggering.
- Negative-space cross-references ("Analysis-only; to harden one use
  `ci-harden-workflow`", "distinct from `pr-review`") that disambiguate sibling
  skills. These prevent the wrong skill from firing and must survive.
- The skill's own name-match cue and its primary "use when …" phrase.

## Scope guards

- **Exclude externally-managed skills** from all edits. Derive the excluded set
  from `.skillshare/config.yaml` ownership metadata (skillshare-installed skills),
  not a single hardcoded name. `ai-hooks-integration` is externally installed via
  skillshare — local edits are overwritten on the next `skillshare install`, so it
  is out of scope. If ownership metadata is unavailable, fall back to the
  `docs/SKILL-NAMING.md` exceptions list intersected with skillshare provenance.
- `graphify`, `help`, `pass-cli` are naming *exceptions* but are locally owned —
  they are **in** scope for efficiency edits (name is not touched; description is).

## Verification (highest-rigor: skill-creator eval harness)

For each **Lever B** trim (content change):

1. Generate a per-skill eval set (JSON of should-trigger and should-not-trigger
   queries) via skill-creator's analyzer agent. The should-not-trigger set
   **includes queries lifted from same-domain sibling skills** (`pr-*`, `ci-*`,
   `docs-*`, …) so the eval detects a trim that makes a neighbor start firing or
   makes the target lose the trigger to a neighbor (cross-skill collision).
2. `run_eval.py --skill-path <dir> --eval-set <json>` on the **original**
   description → baseline trigger/no-trigger rates.
3. `run_eval.py … --description "<trimmed>"` (override, file untouched) → candidate
   rates.
4. **Accept the trim only if** candidate should-trigger rate ≥ baseline **and**
   candidate should-not-trigger (false-fire) rate ≤ baseline. Otherwise revise the
   wording and re-run, or keep the original.

For each **Lever A** conversion (formatting only): no eval. A trigger-phrase diff
confirms the token set is unchanged (folded) or changed only by newline→space
(literal). This is proportionate — the parsed triggering tokens are preserved by
construction.

Tooling location:
`~/.claude/plugins/cache/claude-plugins-official/skill-creator/…/scripts/run_eval.py`
(run as `python3 -m scripts.run_eval` from the skill-creator dir). Interface
verified: `--eval-set`, `--skill-path`, `--description`, `--runs-per-query`,
`--trigger-threshold`, `--model`.

## Durability add-ons (approved)

- **D1 — Ratchet the budget.** After the pass, lower the `context_budget.bats` cap
  from 22,800 to **new_total + ~800 bytes** (~3 average skills of headroom — not
  near-zero, which would break CI on the next legitimate skill). Record the new
  total and rationale in the test's comment block, matching the file's existing
  convention.
- **D2 — House-style note.** Add a short section to `docs/SKILL-NAMING.md`:
  inline single-line descriptions; ~290-char soft norm; double-quote when the text
  contains `: ` or a leading YAML indicator; preserve trigger phrases,
  security keywords, and negative-space cross-references. New skills follow it.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Over-trim silently drops a trigger cue | Eval gate (should-trigger ≥ baseline) on every Lever B change |
| Trim makes a sibling skill fire instead | Sibling-derived negative queries in the eval set |
| Inlining a colon-space description breaks YAML | Quote the 11 identified skills; `yamllint`/parse check in CI |
| Editing an externally-managed skill (reverted upstream) | Exclude by skillshare provenance |
| D1 ratchet too tight → future CI friction | Leave ~800 bytes headroom |
| Literal block was genuine multi-line, merged wrongly | Verified: 0 of 31 are multi-line |

## Expected outcome

~800–1,300 bytes recovered (Lever A ~300–500 free + Lever B ~500–800), all 88
descriptions in one consistent inline house style, every Lever B trim
eval-verified for no triggering regression, and the budget ratcheted to lock the
gain. `context_budget.bats` and `skill_naming.bats` stay green. One focused PR.

## Delivery

Isolated worktree `feat/skill-frontmatter-efficiency` (recreated after the prior
worktree was pruned by a `branch-clean` run). Logical commits: (1) Lever A
formatting, (2) Lever B trims with eval evidence, (3) D1 budget ratchet, (4) D2
doc. Full pre-commit + `context_budget.bats` + `skill_naming.bats` green before PR.
