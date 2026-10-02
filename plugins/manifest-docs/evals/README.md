# manifest-docs evals

20 cases, 5 per skill (4 should-fire, 1 should-not-fire). Headline number is Δ
(with-plugin score minus without-plugin score).

## Run

```bash
claude plugin eval . --ablation with-without --judge-model opus \
  --allow-tools Bash Write Edit --no-publish -j 4
```

`--allow-tools Bash Write Edit` is required: each case's `allowed_tools` is only
a ceiling, the skills grant no tools themselves, and every case except
`10-diag-neg-syntax` creates its fixture repo with Bash and is graded on files
the agent writes. Without the grant, file graders cannot pass in either arm.
`Agent` (used by docs-all's sub-agents in cases 16–19) is not a gated tool; the
case-level `allowed_tools` is enough.

Cases run as `model: sonnet`; the opus judge keeps judge ≠ agent.

## Fixtures

Each prompt opens with a readable `python3 - <<'EOF'` script that writes a small
"tallyho" CLI repo with planted defects (stale defaults, fluff, over-cap pages,
broken links). Graders check those defects, not SKILL.md wording. Should-not-fire
cases (05, 10, 15, 20) also score `tool_used: Skill` with `max: 0, arm: both`
and exact-content regexes that fail on any edit beyond the requested one.

## Regenerating cases

Case directories are generated — edit `_generator/`, not the prompts:

```bash
cd evals/_generator
python3 gen.py .. readme diagrams improve all   # rewrite case dirs; each graders/ is rebuilt
python3 verify.py ..                            # exit 1 on drift or a broken fixture
```

`verify.py` regenerates into a temp dir and fails on any missing, stale, or
edited case file, then runs every setup script against its fixture.

`fixtures.py` holds the "tallyho" repo and planted defects; `gen.py` holds
prompts, budgets, and graders per skill.

## Known limitations

- `troubleshooting-fluff-gone` (cases 16, 17, 19, weight 0.5) reads only
  `docs/TROUBLESHOOTING.md`. A valid run that splits it into
  `docs/troubleshooting/*.md` and deletes the original would fail this grader.
  No run in the 2026-09-27 full suite split it; if one does, switch the grader
  to a trace check over all troubleshooting pages.
- `skill-fired` graders are display-only (excluded from Δ). Several skills do
  not fire on casual prompts (cases 04, 09, 14, 17, 18); that is a plugin
  finding, not an eval defect.
