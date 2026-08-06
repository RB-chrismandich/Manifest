---
name: docs-improve
description: Audit a project's docs set against Diataxis and measured line caps, fixing real gaps and fluff. Use for "improve the docs", "the docs are too long", "audit our documentation".
---

# Improve the Docs Set

Audit `docs/` against Diataxis and the doc concision contract, then fix what you
find. Concision is measured, not judged: read
`../../runtime/references/doc-concision.md` first, and treat
`docs_lint.py` as the arbiter of "too long".

## Parallel Agent Integration

Uses parallel agents CONDITIONALLY when total documentation lines > 500:
`[[skill:parallel-agent]] --json --validate`

## Steps

### 1. Measure first

```bash
python3 ../../runtime/docs_lint.py docs README.md --json /tmp/docs-before.json
```

Exit 1 means at least one doc is over its cap. Record the baseline — the report
at the end must show the delta, not an assertion of improvement.

### 2. Classify every doc

Assign each file one Diataxis quadrant. A file that fits two is two files.

| Type | Orientation | Answers |
|------|-------------|---------|
| Tutorial | Learning | "Teach me, I'm new" |
| How-to | Problem-solving | "How do I do X?" |
| Reference | Information | "What is the exact value of X?" |
| Explanation | Understanding | "Why is it built this way?" |

Mismatch between a file's cap and its real type is a classification bug: fix it
with a `<!-- doc-type: reference -->` marker rather than by fighting the cap.

### 3. Cut fluff, then split

In that order — cutting often brings a page under cap on its own, and splitting
first just distributes the fluff. Both rules are in the concision reference.

- Delete: quality adjectives, difficulty claims, meta-narration, hand-written
  TOCs under ~100 lines, content duplicated from an upstream doc (link it).
- Split over-cap pages by subject into `docs/<topic>/README.md` (hub, ≤120
  lines, one line per child) plus one page per subject. Never `-part-2`.

### 4. Fill real gaps only

Create a missing doc when a reader has a question with no home — not to complete
a checklist. Priority order when several are missing:

| Document | Why it earns its place |
|----------|------------------------|
| `docs/README.md` | Without a hub, sub-pages are unreachable |
| `docs/GETTING_STARTED.md` | First-run path, verified end to end |
| `docs/CONFIGURATION.md` | Every option, actual defaults |
| `docs/TROUBLESHOOTING.md` | Real error strings users will paste |
| `docs/ARCHITECTURE.md` | Why, for the person changing it |

New pages start at the minimum viable shape: title, one-line purpose, content.
Add "Last Updated" and "Related Documents" only where they carry weight — a
three-link "Related" block on a 40-line page is fluff.

### 5. Fix links, then re-measure

Every `[text](path)` must resolve. Every page must be reachable from a hub.

```bash
python3 ../../runtime/docs_lint.py docs README.md --json /tmp/docs-after.json
```

## Report

```text
docs-improve
Caps:   10 over → 2 over   (docs/COMMANDS.md, docs/CONFIGURATION.md remain)
Lines:  6,140 → 3,880
Fluff:  20 hits → 3
Split:  docs/TROUBLESHOOTING.md → docs/troubleshooting/{README,install,auth}.md
Gaps:   created docs/README.md (hub was missing)
Links:  3 broken fixed, 0 orphans
Left:   docs/COMMANDS.md is generated — fix generate_commands_doc.py, not the doc
```

State what is still over cap and why. A run that silently leaves a doc over cap
reads as a pass it did not earn.

## Writing principles

- **Accurate**: document only what exists. No aspirational features.
- **Concise**: the cap is the budget; if it does not fit, it is two pages.
- **Connected**: one hub per topic, no orphans.
- **Current**: if the code moved, the doc is wrong, not merely stale.

## Sub-agent dispatch

Follow `../../runtime/references/sub-agent-dispatch.md` for sub-agent mechanism selection.

Above ~10 docs, fan out one sub-agent per topic directory through
`[[skill:parallel-agent]]`, or use native Task sub-agents on Claude. Dispatch on
**Sonnet** (`subagent_model: sonnet`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.
