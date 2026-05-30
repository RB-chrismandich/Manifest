---
name: token-economy
description: |
  Switch the current session into terse, surgical, clarify-first mode to cut
  token usage. Invoke when responses are verbose, during long refactors, or to
  conserve budget. Opt-in session mutator — re-invoke if it wears off.
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

This mode lives only in the session context. In a long session the invocation
can scroll out of the active window and default verbosity returns — if you
notice that (roughly 30k+ tokens in), re-invoke `/token-economy`. True always-on
enforcement would require a hook (e.g. `ai-hooks-integration`); that is out of
scope for this skill.
