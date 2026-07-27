# Doc Concision Contract

Read before writing or auditing documentation. The caps are machine-readable in
`configs/claude/config/doc_limits.yml`; check them with:

```bash
python3 configs/claude/scripts/docs_lint.py docs README.md
```

Exit 1 means at least one doc is over cap. The fix is always the same: split.

## Caps

| Type | Cap | The one thing it does |
|------|-----|-----------------------|
| hub / index | 120 | Names its children. One line each. Nothing else. |
| root README | 200 | What this is, how to run it, where to go next. |
| tutorial | 200 | One learner, one lesson, start to finish. |
| how-to | 200 | One goal, ordered steps, one working example. |
| explanation | 250 | Why the system is shaped this way. No steps. |
| reference | 400 | Lookup surface. Readers arrive by search and leave. |
| diagram page | 300 | Max 4 diagrams, ≤20 nodes each, caption under each. |

Total lines, `wc -l` parity — code blocks included. A reader scrolling a
900-line page gets no discount for the fences.

Exempt: generated files, vendored trees, and dated records (specs, plans,
reports, ADRs, baselines). A record rewritten to hit a cap is a falsified
record.

## Fan-out

Over cap is a signal that a page holds more than one subject, so split by
subject, never by length.

1. Find the seams. Each H2 that a reader could arrive at directly, with its own
   goal, is a candidate page.
2. Promote the page to a directory: `docs/TOPIC.md` → `docs/topic/README.md`
   plus one file per subject.
3. The hub keeps only: one-paragraph purpose, and one line per child saying
   what question that child answers. If the hub explains anything, it is an
   explanation page wearing a hub's name.
4. Every child is linked from exactly one hub. No orphans, no page reachable
   only by search.
5. Caps apply recursively — a child over 200 splits again.

Bad split: `CONFIGURATION-part-2.md`. Good split: `config/auth.md`,
`config/storage.md` — each answers a question someone actually asks.

Do not split when: the content is one lookup table (splitting hides entries), or
the whole page is under cap and merely feels long.

## Removing fluff

Delete anything whose removal loses no fact. The blocklist lives under `fluff:`
in `doc_limits.yml` and is advisory — it catches wording, you catch the rest.

Cut on sight:

- Quality adjectives that assert instead of show: comprehensive, powerful,
  robust, seamless, best-in-class.
- Difficulty claims the reader makes, not you: simply, just, easily.
- Meta-narration: "In this document we will…", "As mentioned above".
- Hedged filler: "It is important to note that", "Of course", "Basically".
- Restating the heading in the first sentence under it.
- A hand-written table of contents under ~100 lines — the renderer makes one.
- Horizontal rules used as decoration (>3 per 100 lines).
- Anything already true upstream: link it, do not copy it.

Keep, always: the exact command, the actual default value, the real error
string, the constraint that bit someone.

## Rewriting order

Cut before you split. Fluff removal often brings a page under cap on its own,
and splitting first just distributes the fluff across more files.

1. Delete fluff and duplicated upstream content.
2. Re-measure with `docs_lint.py`.
3. Still over? Split by subject into a hub plus children.
4. Re-measure. Fix links. Confirm no orphans.

## Overrides

Both are in-file HTML comments, and both need a rationale after an em dash so
the next reader can evaluate them — the same contract as help-coverage
exemptions:

```markdown
<!-- doc-type: reference -->
<!-- doc-limit: 500 — one flag table; splitting it hides flags from search -->
```

A `doc-limit:` without a rationale is a hard failure, not a warning. An opt-out
nobody can evaluate is worse than no opt-out.
