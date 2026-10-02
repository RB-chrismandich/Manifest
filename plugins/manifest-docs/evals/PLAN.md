# manifest-docs eval plan (draft — Steps 1–2, awaiting Gate 1)

Each case runs twice (with plugin / without) → headline is uplift Δ, not pass rate.
Fixtures: cases have no fixture mechanism assumed, so each prompt opens with a
compact `python3 - <<'EOF'` setup script that writes a small repo ("tallyho", a
click CLI: `tally/cli.py`, `tally/config.py` default `threshold=5`, `tally/ingest.py`,
`tally/store.py` (sqlite), `pyproject.toml`, `Makefile` with `install`/`test` only).
Planted defects are listed per case — graders check those, not SKILL.md prose.

## 1. docs-improve-readme

Good: README ≤200 lines; every default/command traceable to code (threshold=5,
only `make install`/`make test`); overflow moved to a `docs/` file that exists and
is linked; unsourced claims become `TODO`; report shows lines before→after.
Bad: invents steps (`pip install tallyho` from PyPI, `make docker`); keeps stale
default; deletes custom sections instead of relocating; links to missing files.

| slug | shape | prompt (short) | planted |
|---|---|---|---|
| readme-01-bloated | bloated README | "our README is too long, fix it" | 340 lines, fluff, 60-row config table |
| readme-02-missing | no README | "write a README for this repo" | code only |
| readme-03-stale | under-cap, wrong facts | "README's out of date with the code" | threshold=10, `make docker`, broken link |
| readme-04-onboarding | casual | "new hires can't get this running from the README, clean it up" | missing install step, stale default |
| readme-neg-typo | NOT fire | "fix the typo 'recieve' in README.md" | must stay a 1-word edit |

## 2. docs-generate-diagrams

Good: Mermaid blocks that parse; node names = real modules; ≤4 diagrams/page,
≤20 nodes; over-cap page split into `docs/diagrams/README.md` + subject pages;
stale components removed. Bad: invented components, one "everything" diagram,
`part-2` naming, stale redis node kept.

| slug | shape | prompt (short) | planted |
|---|---|---|---|
| diag-01-fresh | none exist | "add architecture diagrams" | no docs/ |
| diag-02-huge | over-cap page | "the diagram doc is huge" | 7 diagrams, 420 lines |
| diag-03-stale | stale | "diagrams are out of date since we swapped redis for sqlite" | redis nodes |
| diag-04-sequence | specific ask | "draw how a record flows through ingest to store" | — |
| diag-neg-syntax | NOT fire | "what's the Mermaid syntax for a subgraph?" | no files should be created |

## 3. docs-improve

Good: measured before/after numbers; fluff phrases cut; over-cap page split by
subject with hub; orphans linked from a hub; broken links fixed; names what's
still over cap. Bad: asserts improvement without numbers; `-part-2` splits;
creates checklist docs nobody needs; silently leaves a page over cap.

| slug | shape | prompt (short) | planted |
|---|---|---|---|
| improve-01-overcap | over-cap how-to | "the docs are too long" | TROUBLESHOOTING.md 280 lines + fluff |
| improve-02-orphans | no hub | "improve the docs" | 4 pages, no docs/README.md |
| improve-03-audit | audit ask | "audit our documentation" | mix: 2 broken links, fluff, 1 over cap |
| improve-04-links | casual | "half the links in our docs 404, sort it out" | 3 broken links |
| improve-neg-docstring | NOT fire | "add a docstring to store.save()" | no docs/*.md created |

## 4. docs-all

Good: report states order used + why, each sub-skill outcome, before/after cap
counts, names docs still over cap; docs-improve runs last. Bad: no measured
delta; aborts on one failure; honours a bad `--order` silently.

| slug | shape | prompt (short) | planted |
|---|---|---|---|
| all-01-refresh | full refresh | "refresh all the docs" | bloated README, no diagrams, orphan docs |
| all-02-bad-order | explicit order | "--order docs-improve,docs-improve-readme,docs-generate-diagrams" | must warn |
| all-03-refactor | change signal | "we just split ingest into two modules, update everything" | diagrams-first expected |
| all-04-casual | casual | "docs are a mess across the board, update everything at once" | same as 01 |
| all-neg-readme-only | NOT fire | "update just the README's install section" | no docs/diagrams created |

Totals: 20 cases (16 fire, 4 neg) × 2 arms × runs 3.
