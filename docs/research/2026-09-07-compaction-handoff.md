# Compaction and fresh-session handoff

Date: 2026-09-07. Status: research and proposed policy; not runtime enforcement.

## Decision

Implement evidence-backed checkpointing and a configurable handoff reminder.
Do not enforce an unconditional restart after a fixed compaction count.
Start with **X = 2 confirmed compactions per session** as an experimental
reminder threshold, not a demonstrated model-quality limit. Recommend a new
session at the next safe task boundary. A user-requested handoff or a material
loss of task state can justify an earlier handoff, independent of the count.

This session stops after delivering this research and the next-session goal.
Implementation belongs in the new session.

## Evidence and impact

[OpenAI's compaction guide](https://developers.openai.com/api/docs/guides/compaction)
describes compaction as reducing context size while preserving state for later
turns, balancing quality, cost and latency. Its API compaction items can be
opaque encrypted state, not ordinary readable summaries. Do not assume every
harness implements compaction identically or treat a Markdown checkpoint as a
replacement for a vendor's native compaction output.

[Anthropic's context-engineering report](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
describes compaction and persistent notes as useful for long-running work. It
also warns that aggressive compression can omit subtle, important information.
This supports preserving decisions and source references, not treating all
compaction as failure.

[Codex configuration documentation](https://learn.chatgpt.com/docs/config-file/config-reference)
exposes `model_auto_compact_token_limit`, a token threshold for automatic
compaction, and `model_context_window`. Neither is a count of compactions or
evidence that a session should restart after a particular number.

None of these inspected sources establishes a universal safe number of
compactions. The proposed value of two is a tunable operational hypothesis.
A new session also needs to reconstruct context and can inherit an inaccurate
summary. It is not intrinsically more correct. Re-reading authoritative files
and preserving test evidence are the important safeguards.

Expected trade-off, to be measured: a handoff may reduce irrelevant accumulated
context but adds checkpoint, startup, and re-verification work. No performance
gain or token saving has been measured for Manifest in this investigation.

## Manifest observations

Inspected at commit `2f8ee812` on `main`, with existing uncommitted Jules work:

- `plugins/manifest-workspace/skills/session-checkpoint/SKILL.md` already calls
  for XDG-state checkpoints with objectives, constraints, tree state, tests,
  unresolved findings and next actions. Extend this seam; do not add a competing
  checkpoint system.
- Its `references/summary-template.md` still presents a 95% trigger and assumes
  a context-usage warning. Missing telemetry must be represented as unknown,
  not invented usage or zero compactions.
- `plugins/manifest-workspace/agents/orchestration/context-chronicler.md` has a
  smaller JSON schema without explicit verification results, working-tree
  identity, or live-operation ownership. Align these representations.
- Installed `~/.manifest/skills/session-checkpoint/SKILL.md` differs from the
  source version. It uses scratchpad and memory instructions. Reconcile through
  the supported deployment path after source changes; do not hand-edit copies.
- The inspected hook reference lists a Claude `PreCompact` event. A pre-event
  proves an attempt, not successful completion. Actual event availability and
  semantics need per-harness verification before implementing a counter.

Total thread token consumption does not establish current context occupancy or
compaction count. The actual total compaction count of this thread is unknown.

## Proposed behavior and enforcement boundary

1. **Observe:** Count only confirmed, session-scoped compaction events from a
   supported harness adapter. Deduplicate event identities; exclude child-agent
   events and failed attempts. Report unsupported telemetry as unknown. Do not
   scrape private transcripts by default or infer counts from token totals.
2. **Preserve:** At observed compaction boundaries and before a handoff, write
   an atomic, private checkpoint with the original goal, constraints, decisions,
   repository/branch/HEAD, dirty-tree inventory, completed and remaining work,
   evidence paths/results, unresolved uncertainty, and one next action. Keep
   secrets and full transcripts out. Surface persistence failures.
3. **Recommend:** At two confirmed compactions, offer one reminder per session
   at a safe boundary, with checkpoint path and a copyable next-session goal.
   Support configuration and explicit deferral. Do not repeat a dismissed
   reminder every turn. Do not auto-launch a second session or duplicate work.
4. **Handoff safely:** On an accepted handoff, stop starting new work after
   saving state. Verify live jobs and record ownership, handles and monitoring
   obligations before stopping. Do not kill, restart, abandon monitoring, or
   claim completion merely to satisfy the threshold. The new session checks
   current files, Git state and live handles before acting on checkpoint claims.
5. **Enforce narrowly:** Validate checkpoint integrity and continuation
   preconditions where Manifest owns the execution path. Elsewhere, disclose
   that guidance is advisory. Do not install a global hard-stop gate until
   telemetry, safe-boundary handling and measured benefit justify one. Unknown
   telemetry must not block ordinary work or bypass existing safety gates.

Evaluate uninterrupted native compaction against checkpoint-plus-handoff on
the same representative tasks. Measure missed constraints, repeated completed
work, duplicate actions, verification failures, recovery time, tokens and
latency. Keep two configurable until outcomes justify changing the threshold
or enforcement mode; do not call unit tests evidence of improved model quality.

## Next-session goal

> Improve Manifest's session continuity using this research. Extend the existing
> session-checkpoint skill and context-chronicler contract with an evidence-backed
> handoff policy. Verify each supported harness's compaction telemetry; where
> reliable, track deduplicated completed compactions per session and recommend a
> fresh session after a configurable default of two, at a safe boundary. Where
> telemetry is unavailable, report unknown and retain manual handoff. Persist a
> private atomic checkpoint and copyable continuation goal; preserve the original
> objective, constraints, Git/dirty-tree state, test evidence, unresolved issues,
> and ownership of live operations. Revalidate these in the next session. Support
> deferral without repeated reminders; never auto-restart, duplicate actions,
> abandon monitoring, or claim task completion because a threshold was reached.
> Align source skills, templates, agents and generated mirrors, add isolated
> tests for boundaries, duplicate/failed events, unavailable telemetry, deferral,
> persistence failures and active jobs, and document per-harness enforcement
> limits. Use evaluation results before proposing mandatory restart enforcement.
> Preserve all existing Jules changes; do not commit, push, deploy, or launch
> cloud tasks without separate authorization.

## Handoff state

Repository: `/Users/charlemagne/agentic-workstreams/internal/Manifest`.
Current branch and HEAD were read directly: `main`, `2f8ee812`.
`git status --short` confirms the Jules changes remain uncommitted, including
the deletion of `.github/workflows/jules-trigger.yml` and new remote-delegation
modules/tests. Do not discard or include them in an unrelated commit.

Earlier in this turn, the Jules verification commands completed with 315 Python
tests and 33 Bats tests passing. Those are Jules regression results, not tests
of the proposed compaction policy. No runtime compaction policy was changed.
The Python and Bats process handles terminated with exit zero; no new Jules
cloud task was launched. Do not infer that all unrelated external jobs are idle.

First action in the new session: read this file and `git status --short`, then
inspect the checkpoint source and supported harness event interfaces.
