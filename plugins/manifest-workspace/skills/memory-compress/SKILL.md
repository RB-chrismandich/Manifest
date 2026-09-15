---
name: memory-compress
description: Compress or summarize memory/log entries — distill a session/transcript into a dated one-line entry, or selectively compress/rotate existing memory entries (daily summary, developer-shorthand rewrite, one-sentence log line) while preserving durable source provenance.
---
# Memory Compress

Selective, non-destructive compression of session content into a memory artifact. You compress — you never
create. A summary is a lossy projection of its source: it may drop detail, but it must never invent detail,
drop a required ID/decision, or replace its source before that source's durable copy is verified. Output the
result only — no preamble, no fences, no commentary.

## Provenance gate (read this before touching any existing entry)

Compression that ROTATES or REPLACES existing memory content is a destructive operation gated on durable
source provenance:

1. **Identify the source's durability before compressing it.** Durable: a file already committed to disk/git,
   a prior memory-log entry, a ticket/issue/PR record, or any artifact that survives after this turn ends.
   Ephemeral: only the current conversation transcript, with no durable copy anywhere.
2. **Durable source → rotate/replace is allowed, but only after the archive step is verified.** Write the
   compressed entry to its destination, then confirm the write succeeded (the archived/rotated file exists and
   contains the new entry) before treating the original as superseded. Never delete, truncate, or overwrite the
   original ahead of that verification — if the archive write fails or cannot be confirmed, leave the source
   untouched and report the failure instead of silently keeping only the summary.
3. **Ephemeral-only source → do not rotate or replace anything.** There is nothing durable to fall back on if
   the summary is wrong or incomplete. Produce the summary as a separate, additional artifact (or plain output)
   and explicitly report that no durable source exists for it — the caller decides whether to accept that risk,
   compression does not decide it silently.
4. **Source retention outranks the one-sentence budget.** Mode A's "one sentence" target (below) is a style
   target, not a license to drop a fact that would break provenance. If preserving every required ID/decision
   needs more than one sentence, use more than one sentence rather than lose the fact.

## Shared core

1. **Identify the compression target and its fixed format first.** Common modes: (a) selective consolidation
   with rotation (staging → recent → archive by age threshold), (b) single-entry shorthand rewrite, (c)
   one-sentence daily log line. Copy any pre-computed header (`## HH:MM | branch`) verbatim — never invent
   `## unknown | unknown` or substitute your own values even if a prior entry looks malformed; that is a
   regression.

2. **Preserve every required fact, ref, and relationship — this is not optional lossiness.** Keep all
   PR/issue numbers, file names, function names, commit SHAs, counts, test counts, version bumps (`14→15`),
   decisions made, and causal links ("X caused Y"). If a verb or object naming one of these would be lost,
   it stays, even past the target length.

3. **Everything else is fair game to drop, because this compression is intentionally lossy:** articles
   (a/the/an), prepositions where context is clear, prose connectors, filler ("in order to", "successfully",
   "that handle"), conversation flow, intermediate steps, context-percentage chatter, and any narrative detail
   that is not a required ID or decision from rule 2.

4. **Use shortest-form shorthand that preserves the semantic vector:** conf, env, MR, infra, impl, perm, EM,
   repo, auth, docs, dev, refactor. Never abbreviate unique identifiers (product names, branch names, commit
   hashes). Semicolons separate facts within one entry; parentheses carry context (`script.sh (dev detect via
   git conf)`).

5. **Respect the destination's structure.** Honor stated token caps per section (subordinate to the
   provenance gate above), keep the required headers (`## timestamp | branch`), maintain chronological order
   (oldest→newest), and append/rotate exactly as specified.

6. **Never add content not present in the source.** No new opinions, no inferred detail, no invented refs, no
   fabricated IDs. If a required fact is missing from the source, say it is missing — do not guess a
   plausible-looking value to fill the gap.

## Mode A — Distill a single session into one entry

- **One sentence, specific, subject to the provenance gate.** Name concrete artifacts: files, function names,
  PR/MR numbers, issue numbers, commit hashes, test counts. Apply the shared compression rules to that
  sentence; if the session's transcript is the only source (ephemeral, no durable copy), this entry IS the
  durable artifact being created — that is compression's normal job here, not a provenance violation.
- **SKIP detection.** If the session covers the same work as the previous entry with no meaningful new
  progress, output exactly the agreed sentinel (e.g. `SKIP`) and nothing else. A pure follow-up (e.g. a
  security re-check that found nothing on the same feature) is a SKIP.
- Output only the entry block — no preamble.

## Mode B — Compress existing entries (rotation/replacement)

- Every entry rewritten here already has a durable source (it is itself a prior committed memory-log entry),
  so the provenance gate is satisfied by construction — but verify the rotation/archive write before treating
  the pre-rotation file as superseded (gate step 2).
- **Merge entries about the same work into one time-blocked entry** (e.g. `08:48-09:22`), grouped by subject
  (feature/issue/file). Collapsing five entries about one feature into one is the biggest compression win. Do
  NOT merge work that is genuinely distinct (different branch, hours apart, different phase) just because it
  shares a topic.
- Preserve the `## timestamp | branch` format and chronological order throughout.

> Absorbed: session-memory-digest (2026-06); merged from the former memory-log-compress and
> session-memory-compress skills (specs/480, 2026-07). Scope note (2026-09): this skill governs memory-log
> compression only; it does not touch `manifest-workspace:session-checkpoint`'s
> compaction-continuity artifacts.
