---
name: memory-log-compress
description: Use when asked to compress memory/log entries into developer shorthand, or to distill a session transcript into one time-stamped log entry, with zero information loss.
---
# Memory Log Compress

Two related modes for maintaining a terse, chronological memory/activity log. Output the result only — no preamble, no fences, no commentary.

## Mode A — Compress existing entries

1. **Preserve every fact, ref, verb, and relationship.** Zero information loss is the hard constraint; compression is non-destructive.
2. **Drop only noise:** articles (a/the/an), prepositions where context is clear, filler ("in order to", "successfully"), and prose connectors.
3. **Use shortest-equivalent forms:** conf, env, impl, infra, perm, MR, EM, repo, etc. — any abbreviation that preserves the same semantic vector for an LLM reader.
4. **Group by subject.** Merge multiple entries about the same issue/feature/file into ONE time-blocked entry (e.g. `08:48-09:22`). This is the biggest win — collapse five entries about one skill into one. Do NOT merge work that is genuinely distinct (different branch, hours apart, different phase) just because it shares a topic.
5. **Use parentheses for context** (`script.sh (dev detect via git conf)`) and **semicolons** to separate facts within an entry.
6. **Preserve the `## timestamp | branch` header format** and keep entries in oldest→newest order.

## Mode B — Distill a session into ONE entry

1. **Copy the provided header verbatim** (`## HH:MM | branch`). These are pre-computed concrete values — never invent your own, and never regress to `## unknown | unknown`.
2. **Write exactly one sentence:** what was done, with specific refs (files, PR numbers, issue numbers, commit SHAs).
3. **Apply the same compression** (shortest-form words, drop filler) and keep all specifics.
4. **Return the literal word `SKIP`** (nothing else) if the session covers the same work as the previous entry with no meaningful new progress.
