---
name: parallel-agent
description: Run installed agent harness CLIs in parallel for review, analysis, synthesis, and structured cross-verification without bootstrap or shared-home runtime files.
---

# Parallel Agent

Run `scripts/parallel_agent.py` from this skill. The executable reads immutable
JSON configuration and prompts adjacent to itself and writes mutable run output
below `$XDG_STATE_HOME/manifest/agent-outputs/`.

It may invoke harness CLIs already installed on `PATH`. It must never install a
harness, call an ephemeral coordinator, read a sibling plugin, or resolve a
shared assistant-home script/config tree.

Use `--json` for structured result parity with existing consumers. Common modes
are `--review FILE`, `--analyze FILE`, `--improve FILE`, and a positional prompt;
add `--validate` for the bundled two-tier validation registry.

If the current harness cannot return structured skill output, perform the same
review inline and report `DEGRADED` with the unavailable capability.
