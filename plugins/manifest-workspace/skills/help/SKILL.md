---
name: help
description: Use when you need to find the right Manifest command for a task — searches and lists every command by category with a one-line description and when-to-use cue, flagging ones unavailable here. Read-only; never runs or modifies.
---

# Command Discovery (`/help`)

Interactive, read-only discovery surface over every command in this repository.
Backed by `~/.claude/scripts/command_catalog.py` (the machine catalog built from
each skill's `SKILL.md` frontmatter — the single source of truth). This skill
never runs, installs, or modifies anything; it only lists and searches.

## How to run it

Invoke the catalog CLI and show the user its output verbatim:

```bash
# Full listing, grouped by category (bounded; a footer shows how to narrow):
~/.claude/scripts/command_catalog.py

# Intent / keyword search (ranked: name > category > description/when-to-use):
~/.claude/scripts/command_catalog.py "<query>"

# Restrict to one taxonomy category:
~/.claude/scripts/command_catalog.py --category <key>

# Include commands unavailable in this environment (shown with a reason):
~/.claude/scripts/command_catalog.py --all

# Widen a truncated listing:
~/.claude/scripts/command_catalog.py --limit 100
```

Argument mapping from the `/help` invocation (`/help [query] [--category <key>]
[--all] [--limit <N>]`):

| User typed | Run |
|------------|-----|
| `/help` | `command_catalog.py` |
| `/help branches` | `command_catalog.py branches` |
| `/help --category security` | `command_catalog.py --category security` |
| `/help --all` | `command_catalog.py --all` |

## Behavior contract (see contracts/discovery-command.md)

- **Empty query** → full listing grouped by category (`order` asc, uncategorized
  last). Each row: `` `/name` — description _(when to use)_ ``.
- **Query present** → ranked matches; ties broken alphabetically.
- **No match** → the CLI prints `No command matches "<query>".` Relay it as-is;
  never invent a substitute suggestion.
- **Unavailable commands** are hidden by default and never recommended first;
  `--all` reveals them with a reason (FR-008).
- **Bounded output** — results are capped at a default row limit with a
  `… N more — narrow with /help <query>` footer, so a single turn never dumps
  the whole catalog (context-budget guard). Raise with `--limit`.
- **Deterministic & offline** — no model call; identical input → identical
  output. The listing is one-shot output, not added to always-loaded context.

If the catalog CLI exits non-zero, surface its stderr (it names the offending
`SKILL.md` for a malformed/duplicate/empty skill) rather than guessing.
