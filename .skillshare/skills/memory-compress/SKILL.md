---
name: memory-compress
description: Compress or summarize memory/log entries — distill a session/transcript into a dated one-line entry, or losslessly compress/rotate existing memory entries (daily summary, developer-shorthand rewrite, one-sentence log line) with zero information loss.
---
# Memory Compress

Mechanical, non-destructive compression of session content into a memory artifact. You compress — you never create. Zero information loss on facts, refs, verbs, and causal links. Output the result only — no preamble, no fences, no commentary.

## Shared core

1. **Identify the compression target and its fixed format first.** Common modes: (a) full consolidation with rotation (staging → recent → archive by age threshold), (b) single-entry shorthand rewrite, (c) one-sentence daily log line. Copy any pre-computed header (`## HH:MM | branch`) verbatim — never invent `## unknown | unknown` or substitute your own values even if a prior entry looks malformed; that is a regression.

2. **Preserve every fact, ref, and relationship.** Keep all PR/issue numbers, file names, function names, commit SHAs, counts, test counts, version bumps (`14→15`), and causal links ("X caused Y"). If a verb or object would be lost, it stays.

3. **Drop only noise:** articles (a/the/an), prepositions where context is clear, prose connectors, filler ("in order to", "successfully", "that handle"), conversation flow, intermediate steps, and context-percentage chatter.

4. **Use shortest-form shorthand that preserves the semantic vector:** conf, env, MR, infra, impl, perm, EM, repo, auth, docs, dev, refactor. Never abbreviate unique identifiers (product names, branch names, commit hashes). Semicolons separate facts within one entry; parentheses carry context (`script.sh (dev detect via git conf)`).

5. **Respect the budget and structure.** Honor stated token caps per section, keep the required headers (`## timestamp | branch`), maintain chronological order (oldest→newest), and append/rotate exactly as specified.

6. **Never add content not present in the source.** No new opinions, no inferred detail, no invented refs. Output raw signal only — developer shorthand, no prose, no preamble, no markdown fences.

## Mode A — Distill a single session into one entry

- **One sentence, specific.** Name concrete artifacts: files, function names, PR/MR numbers, issue numbers, commit hashes, test counts. Apply the shared compression rules to that sentence.
- **SKIP detection.** If the session covers the same work as the previous entry with no meaningful new progress, output exactly the agreed sentinel (e.g. `SKIP`) and nothing else. A pure follow-up (e.g. a security re-check that found nothing on the same feature) is a SKIP.
- Output only the entry block — no preamble.

## Mode B — Compress existing entries (lossless)

- **Merge entries about the same work into one time-blocked entry** (e.g. `08:48-09:22`), grouped by subject (feature/issue/file). Collapsing five entries about one feature into one is the biggest compression win. Do NOT merge work that is genuinely distinct (different branch, hours apart, different phase) just because it shares a topic.
- Preserve the `## timestamp | branch` format and chronological order throughout.

> Absorbed: session-memory-digest (2026-06); merged from the former memory-log-compress and session-memory-compress skills (specs/480, 2026-07).
