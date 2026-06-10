---
name: session-memory-compress
description: Use when compressing a session/log into a memory entry — daily summary, shorthand rewrite, rotation, or one-sentence log line — with zero information loss.
---
# Session Memory Compress

Mechanical, non-destructive compression of session content into a memory artifact. You compress — you never create. Zero information loss on facts, refs, verbs, and causal links.

1. **Identify the compression target and its fixed format first.** Common modes: (a) full consolidation with rotation (staging → recent → archive by age threshold), (b) single-entry shorthand rewrite, (c) one-sentence daily log line. Copy any pre-computed header (`## HH:MM | branch`) verbatim — never invent `## unknown | unknown`.

2. **Preserve every fact, ref, and relationship.** Keep all PR/issue numbers, file names, commit SHAs, counts, version bumps (`14→15`), and causal links ("X caused Y"). If a verb or object would be lost, it stays.

3. **Drop only noise:** articles (a/the/an), prepositions where context is clear, prose connectors, filler ("in order to", "successfully", "that handle"), conversation flow, intermediate steps, and context-percentage chatter.

4. **Use shortest-form shorthand that preserves the semantic vector:** conf, env, MR, infra, impl, perm, EM, repo, auth, docs, dev, refactor. Semicolons separate facts within one entry; parentheses carry context (`script.sh (dev detect via git conf)`).

5. **Merge entries about the same work into one time-blocked entry** (e.g. `08:48-09:22`). Collapsing five entries about one feature into one is the biggest compression win. Maintain chronological order, oldest to newest.

6. **Respect the budget and structure.** Honor stated token caps per section, keep the required headers, and append/rotate exactly as specified. If a new session covers the same work as the previous entry with no new progress, emit the agreed sentinel (e.g. `SKIP`) rather than a redundant entry.

7. **Never add content not present in the source.** No new opinions, no inferred detail, no invented refs.
