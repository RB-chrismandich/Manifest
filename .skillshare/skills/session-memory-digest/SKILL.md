---
name: session-memory-digest
description: Turn a Claude Code session transcript into a one-line dated daily-memory entry, or losslessly compress a set of existing memory entries. Use for daily memory-log maintenance.
---
# Session Memory Digest & Compression

Use for two daily-memory operations: (A) summarize one session into a single dated log entry, or (B) compress a batch of existing entries without losing information.

## Mode A — Summarize a session into one entry

1. **Preserve the exact header.** The first line must be the literal `## <time> | <branch>` header given to you, copied verbatim. Never invent `## unknown | unknown` or substitute your own values even if a prior entry looks malformed — that is a regression.
2. **One sentence, specific.** Name concrete artifacts: files, function names, PR/MR numbers, issue numbers, commit hashes, test counts.
3. **Apply non-destructive compression** (see Mode B rules) to that sentence.
4. **SKIP detection.** If the session covers the same work as the previous entry with no meaningful new progress, output exactly `SKIP` and nothing else. A pure follow-up (e.g. a security re-check that found nothing on the same feature) is a SKIP.
5. Output only the entry block — no preamble, no markdown fences.

## Mode B — Compress existing entries (lossless)

1. **Keep every fact, ref, verb, and causal link.** Zero information loss. Drop only articles, clear-from-context prepositions, filler, and prose connectors.
2. **Shortest semantic-preserving form**: conf, env, MR, infra, impl, perm, EM, repo, etc. Never abbreviate unique identifiers (product names, branch names, commit hashes).
3. **Group by subject — the biggest win.** Merge multiple entries about the same feature/issue/file into ONE time-block entry with a range header (e.g. `## 23:22-23:47 | branch`). Use semicolons to separate facts within an entry; parentheses for context.
4. **Preserve `## timestamp | branch` format and chronological order** (oldest→newest).
5. Output raw signal only — developer shorthand, no prose, no preamble.
