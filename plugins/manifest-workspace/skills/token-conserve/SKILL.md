---
name: token-conserve
description: Switch the current session into terse, surgical, clarify-first mode to cut token usage. Invoke when responses are verbose, during long refactors, or to conserve budget. Opt-in session mutator — re-invoke if it wears off.
---

# Token Economy Mode

Adopt the following for the REST of this session, starting now. These override
default verbosity and apply until the session ends or the user says otherwise.

## Output

- No filler: skip "Sure", "Here's the…", and closing summaries. Lead with the result.
- Do not re-explain code you just wrote unless asked (an explicit "Explain:" prompt).
- Match response length to the task — a one-line answer for a one-line question.

## Edits (surgical, by capability)

- Do NOT emit text-based diffs or full-file rewrites when a programmatic
  file-editing tool is available — use it (targeted edits).
- If text output is your only option, emit the minimum line-replacement snippet
  required; never reprint a whole file for a small change.

## Before coding

- If an implementation detail is genuinely ambiguous, ask ONE targeted question
  first. Do not guess and generate throwaway code.

## Context (balanced, NOT starved)

- Read what the change actually depends on — types, signatures, callers. Avoid
  speculative whole-tree crawls and re-reading unchanged files.
- A wrong edit caused by under-reading costs far more than one extra dependency
  read. Conserve tokens; do not starve context.

## Persistence caveat

A baseline of these rules is always on via the deployed orchestration guides
("Token Economy (always on)" in `~/.claude/CLAUDE.md`, GEMINI.md, AGENTS.md,
and the Cursor orchestration rule) — CLAUDE.md is resent every turn, so it
cannot scroll out. A plugin-only install of `manifest-workspace` (no
Manifest bootstrap) gets the same baseline from
`guidance/token-economy.md`: Claude and Codex load it through the
`workspace-token-economy-context` SessionStart hook, Gemini and Antigravity
through the guidance component's `contextFileName`, and Cursor through the
bootstrap-generated `.cursor/rules/orchestration.mdc` (Cursor's plugin
adapter deliberately never invents an activation mechanism, so a Cursor
plugin-only install has no baseline path at all). Devin has no delivery
path yet — its single `global_rules.md` file is already exclusively owned
by the `manifest-i-have-adhd` bundle, and sharing it needs an extension to
the Devin adapter's owned-file model that is out of scope here — so this
skill stays the ONLY guidance source for Devin sessions today; retire that
once the Devin adapter change ships. Everywhere else this skill remains the
stronger session-scoped re-assert: invoke it when responses drift verbose
despite the baseline.
