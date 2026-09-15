---
name: docs-generate-diagrams
description: Generate and maintain Mermaid architecture diagrams that match current code, capped at 4 diagrams and 300 lines per page — more than that fans out to one page per subject. Use for "add architecture diagrams", "the diagram doc is huge".
---

# Generate Architecture Diagrams

Diagrams that reflect what the code does now. A diagram page is capped at 300
lines and 4 diagrams; past that it becomes a hub plus one page per subject.
Rules: `../../runtime/references/doc-concision.md`. Mermaid syntax traps and
the palette: [references/mermaid.md](references/mermaid.md).

## Sub-agent dispatch

This skill uses the shared OMP dispatch contract in
`../../runtime/references/sub-agent-dispatch.md`: submit all ready independent
units in one `task` call, in waves of at most 32; children execute directly and
never redispatch; use `hub` only to coordinate or wait; and the parent validates
and aggregates evidence. If `task` is unavailable, work inline and report
`DEGRADED`.

Use native OMP sub-agents **conditionally** when analyzing 5+ unique
imports/modules. Dispatch one read-only `scout` per independent module group in
one OMP `task` call (waves of at most 32); children report their assigned
structure and never re-dispatch. The parent reconciles that evidence directly
with the code before publishing diagrams. If OMP `task` is unavailable, inspect
the module groups inline and report `DEGRADED`.

## Steps

### 1. Read the code, not the old diagrams

Entry points, service/client boundaries, provider or adapter implementations,
config loading. A diagram redrawn from a stale diagram inherits its errors.

### 2. Pick the smallest set that answers a real question

Draw a diagram only when prose cannot carry the shape. Start here:

| Diagram | Type | Answers |
|---------|------|---------|
| Application architecture | flowchart | "What happens end to end?" |
| Integration flow | sequence | "Who calls what, in what order?" |
| Component architecture | class | "What implements this interface?" |
| State lifecycle | state | "What states can this entity be in?" |

Add decision-flow, data-model, or config-layer diagrams only when someone has
actually asked. Four per page is the ceiling.

### 3. Keep each diagram readable

- ≤20 nodes. More than that is two diagrams.
- One concept per diagram — no "everything" diagram.
- `LR` for chains and timelines, `TB` for hierarchies and decisions.
- Subgraphs group by logical category, not by file layout.
- Two to four lines of caption under each: what to look at, and why.

### 4. Fan out when over cap

`docs/ARCHITECTURE_DIAGRAMS.md` holding 20 diagrams is a hub in denial. Split
into `docs/diagrams/README.md` (≤120 lines, one line per child) plus one page
per subject — `ingest.md`, `deploy.md`, `config.md`. Name by subject, never
`part-2`.

### 5. Verify rendering, then measure

Every diagram must render — check syntax against
[references/mermaid.md](references/mermaid.md) and preview in the target
platform's markdown. A broken diagram is worse than no diagram: it renders as a
wall of error text.

```bash
python3 ../../runtime/docs_lint.py docs/diagrams
```

## Report

```text
docs-generate-diagrams
Page:     docs/ARCHITECTURE_DIAGRAMS.md 1678 lines / 20 diagrams
Split:    → docs/diagrams/{README,pipeline,deploy,config,state}.md (all under cap)
Redrawn:  3 diagrams now match code (provider list was 2 versions stale)
Dropped:  4 diagrams no concrete reader question mapped to
Rendering: 12/12 verified in GitHub preview
```

## Notes

- Ensure diagrams match actual code structure — verify node names against real
  module and class names.
- The parent reconciles each returned module analysis directly against the code;
  agreement is based on that evidence, not prose similarity.
