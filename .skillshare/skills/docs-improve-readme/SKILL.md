---
name: docs-improve-readme
description: Improve or create a repository README from code-derived facts, held to a 200-line cap — anything past the first ten minutes moves to docs/ and gets linked. Use for "fix the README", "our README is too long".
---

# Improve the README

A README answers three questions: what is this, how do I run it, where do I go
next. Everything else belongs in `docs/` behind a link.

The cap is 200 lines, enforced by `docs_lint.py`; the split and fluff rules are
in `configs/claude/references/doc-concision.md`. Read it first.

## Steps

### 1. Measure

```bash
python3 configs/claude/scripts/docs_lint.py README.md
```

### 2. Derive facts from code, not from the old README

Every claim must trace to something on disk:

| Section | Source of truth |
|---------|-----------------|
| What it is | main module docstring, AGENTS.md |
| Requirements | requirements.txt, package.json, pyproject.toml |
| Quick start | the setup script / Makefile targets that actually exist |
| Configuration | the config file's own keys and defaults |
| Usage | the entry point's real flow |
| Testing | the test commands CI runs |

If a claim has no source, it is not a claim. Mark it `TODO` rather than
guessing — a confident wrong default costs more than a gap.

### 3. Write to the cap

- **Title + description**: 1-3 lines. What it does, why it exists. No
  marketing adjectives.
- **Quick start**: 4-6 steps, copy-pasteable, ending in something that runs.
- **Key features**: 5-10 one-line bullets, or drop the section.
- **Requirements**: versions and external services only.
- **Configuration**: the 5 options most people change. The full table lives in
  `docs/CONFIGURATION.md`.
- **Everything else**: a link.

Sections a README does not need: an exhaustive option table, a full directory
tree, a changelog, a roadmap, badges past the ones people act on.

### 4. Fan out what does not fit

Over cap means content is in the wrong file, not that the README is
under-written. Move whole sections out:

| Overgrown section | Moves to |
|-------------------|----------|
| Full config table | `docs/CONFIGURATION.md` |
| Install variants, first-run walkthrough | `docs/GETTING_STARTED.md` |
| Error/fix table | `docs/TROUBLESHOOTING.md` |
| Directory tree, design rationale | `docs/ARCHITECTURE.md` |

Leave a one-line pointer where the section was. Create the target doc if it
does not exist; never move content into a link that 404s.

### 5. Validate

- Every relative link resolves.
- Every command in a code block runs as written.
- Code fences declare a language.
- Re-run `docs_lint.py README.md` — exit 0.

## Report

```text
docs-improve-readme
Lines:  464 → 186 (cap 200)
Moved:  config table → docs/CONFIGURATION.md; error table → docs/TROUBLESHOOTING.md
Fixed:  2 stale defaults, 1 broken link
Fluff:  4 hits → 0
TODO:   Windows install path unverified — no script on disk
```

## Notes

- **Preserve custom content**: keep project-specific sections the author added;
  relocate them rather than deleting them.
- **Update defaults**: a default in the README that disagrees with the code is
  the most expensive kind of doc bug. Check each one.
