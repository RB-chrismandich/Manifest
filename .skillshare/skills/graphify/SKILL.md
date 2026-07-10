---
name: graphify
description: "Map a codebase, docs, or GitHub repo into a queryable knowledge graph (graphify CLI): graph.html, GRAPH_REPORT.md, graph.json. Use to understand large or unfamiliar code, or answer \"what connects X to Y?\"."
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
# The semantic pass (docs/papers/images, community naming) routes through the
# authenticated Claude Code CLI — see Phase 2. A pure-code corpus does not need
# it, but warn so a mixed corpus doesn't hard-`exit 1` on a missing backend.
if ! command -v claude >/dev/null 2>&1; then
    echo "note: 'claude' CLI not on PATH — AST/code extraction still works keyless,"
    echo "but docs/images need it. Install Claude Code + run 'claude' once to auth,"
    echo "or pass an API-key backend (e.g. --backend gemini with GEMINI_API_KEY)."
fi
```

### Phase 2: Run

Invoke graphify against the requested target, passing through user options.
**Default to the `claude-cli` backend** so the semantic pass runs on our
authenticated Claude Code session — no separate API key:

```bash
# Map a directory or repo (default: current directory). Route the semantic pass
# through the local `claude -p`; haiku keeps structured-JSON extraction fast/cheap.
GRAPHIFY_CLAUDE_CLI_MODEL=haiku graphify "${DIRECTORY:-.}" --backend claude-cli $EXTRA_FLAGS

# Or answer a question against an existing graph (no backend needed)
graphify query "what connects auth to the database?"
```

Why `--backend claude-cli`: code extraction is deterministic (tree-sitter,
keyless), but **docs, papers, images, and community naming need an LLM**.
Running `graphify <dir>` with no backend hard-`exit 1`s on any such file
("no LLM API key found"). `--backend claude-cli` shells out to the locally
installed `claude -p`, authenticating via the user's Claude Pro/Max
subscription (billed to the plan, **not** a pay-as-you-go `ANTHROPIC_API_KEY`).
`GRAPHIFY_CLAUDE_CLI_MODEL=haiku` picks the cheap/fast model for the JSON
extraction; unset it to fall back to the CLI default (Opus). A **pure-code**
corpus needs no backend — plain `graphify <dir>` is fine there.

If the run finishes with `next: run graphify cluster-only <dir>`, do that pass
(also `--backend claude-cli`) to name communities and write `GRAPH_REPORT.md`.

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
