---
name: graphify
description: |
  Map a codebase, docs, or GitHub repo into a queryable knowledge graph (graphify
  CLI): graph.html, GRAPH_REPORT.md, graph.json. Use to understand large or
  unfamiliar code, or answer "what connects X to Y?".
---

# Graphify Skill

Thin wrapper over the `graphify` CLI (PyPI package `graphifyy`, installed by
`bootstrap.sh` when graphify is enabled). It builds and queries a semantic
knowledge graph of a directory or repository. Read-only analysis — it never
modifies your source files.

> Manifest manages graphify as a deployed skill + CLI. Do **not** run
> `graphify install` — the skill is delivered through Manifest's
> `.skillshare/skills/` pipeline, and graphify's own installer would patch each
> assistant's `CLAUDE.md`/`GEMINI.md` out-of-band.

## Arguments

`$ARGUMENTS` — a path or GitHub URL to map (default: current directory `.`),
optionally followed by graphify flags (e.g. `--mode deep`, `--update`,
`--no-viz`) or a subcommand (`query "<question>"`, `path NodeA NodeB`,
`explain <Entity>`).

## Instructions

### Phase 1: Preflight

Verify the CLI is installed; if not, report clearly and stop (do not error out):

```bash
if ! command -v graphify >/dev/null 2>&1; then
    echo "graphify is not installed. Enable it with:  ./bootstrap.sh --enable-graphify"
    echo "(or install manually:  uv tool install graphifyy)"
    exit 0
fi
```

### Phase 2: Run

Invoke graphify against the requested target, passing through user options:

```bash
# Map a directory or repo (default: current directory)
graphify "${DIRECTORY:-.}" $EXTRA_FLAGS

# Or answer a question against an existing graph
graphify query "what connects auth to the database?"
```

The default `host-agent` backend uses the running assistant session as the LLM —
**no API key is required**; code extraction is deterministic (tree-sitter).

### Phase 3: Report

Summarize the outputs graphify wrote to `graphify-out/`:

- `GRAPH_REPORT.md` — god nodes (most-connected concepts), surprising
  cross-module connections, suggested questions.
- `graph.json` — the queryable graph (source of truth for `graphify query`).
- `graph.html` — interactive visualization (unless `--no-viz`).

Point the user at these paths; do not paste large outputs inline.

## Safety

- Read-only: never modify source files; graphify only writes under `graphify-out/`.
- Validate the target path/URL before invoking; do not pass unsanitized input to a shell.
- If the CLI is missing or a backend is unavailable, report the gap with the
  install/enable hint rather than failing silently.
