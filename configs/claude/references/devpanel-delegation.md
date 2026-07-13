# DevPanel Delegation Policy (critic-gated dev/debug/test role agents)

Read this before delegating implementation, debugging, or testing work to the devpanel
role agents. Unlike [pilotfish](pilotfish-delegation.md) — which routes work to the
*cheapest capable* model tier — devpanel is a **quality-gating** scheme: every primary's
output is gated by two independent adversarial validators before it's considered done.
Opt-in (`bootstrap.sh --enable-devpanel`); deploys to both the Claude home
(`~/.claude/agents/`) and the Cursor home (`~/.cursor/agents/`, Cursor-native
frontmatter — see `configs/claude/scripts/generate_cursor_agents.py`), independently of
and alongside pilotfish (disjoint filenames in the same target directory; both toggles
may be enabled together). Gemini/Codex/Antigravity remain out of scope (no subagent-file
mechanism to deploy to).

## Roles

| Role | Kind | Delegate for |
|------|------|---------------|
| `developer` | primary | implement features/fixes; refactor under critique |
| `debugger` | primary | root-cause failures (bugs, races, flaky tests, perf regressions) |
| `tester` | primary | exhaustive end-to-end validation (golden path, edge cases, stress, races, perf) |
| `spec-guard` | shared validator | spec/functionality adherence — feature drift, broken dependencies, regressions |
| `chaos-engineer` | shared validator | resilience/performance — edge cases, races, leaks, latency under load |

Pick the primary that matches the job: `developer` to build, `debugger` to diagnose a
failure, `tester` to validate a completed change. The two validators are
**domain-agnostic** and gate *whichever* primary just ran — they are not duplicated
per-primary. This mirrors two existing Manifest patterns rather than inventing a third:
pilotfish's single `verifier` gates both `executor` and `security-executor`; the CDDL
loop (`spec-implement-loop`) gates its one `implementer` with two shared critics
regardless of what's being built.

## Workflow protocol

The three roles interact in a continuous loop:

1. **Primary proposes.** `developer`, `debugger`, or `tester` produces a candidate —
   an implementation, a root-caused fix, or a set of exhaustive test findings.
2. **Validators critique independently.** Both `spec-guard` and `chaos-engineer`
   audit the candidate from their own lane — spec/functionality vs.
   resilience/performance — without assuming the other or a test suite already caught
   something. Each returns `APPROVED` or `REJECTED` with specific, actionable,
   file-anchored findings.
3. **Primary refactors.** The primary addresses **every** finding from **both**
   validators — not a subset, and not by arguing the finding — and re-submits.
4. **Loop.** Repeat steps 2–3 until termination.

## Termination condition

Do **not** mark the work complete, and do not report it as finished, until **all** of
the following hold simultaneously:

- Both `spec-guard` and `chaos-engineer` have explicitly returned `APPROVED` on the
  **same** candidate (an approval on a prior, since-changed candidate does not count).
- Neither validator, nor the primary, can name any additional edge case, optimization,
  or coverage gap left to address.
- The primary (`developer`/`debugger`/`tester`) has **zero pending changes** —
  everything raised has been addressed, not deferred.

Treat a `REJECTED` verdict as a blocker, not a suggestion — the orchestrator does not
proceed past a rejected candidate.

## Relationship to Manifest's existing facilities

This is a distinct, complementary layer, not a replacement:

- **pilotfish** (`pilotfish-delegation.md`) answers "which cost tier should do this
  unit of work" (cheap read-only → expensive judgment/security work). devpanel answers
  "how do I know this specific implement/debug/test output is actually correct and
  robust." A task can be routed through pilotfish for cost tiering and still land in a
  devpanel loop for its final quality gate — they compose, they don't conflict.
- **`spec-implement-loop` (CDDL)** already runs a scripted, spec-gated critic loop
  (`implementer` + `arch-critic` + `qa-critic`) driven by `cddl_loop.py` against a
  completed spec+plan artifact, with its own exit-code contract and run persistence.
  devpanel is **not** that: it is a set of general-purpose, standalone subagents for
  ad hoc implement/debug/test work with no spec-artifact prerequisite, dispatched
  directly via the `Agent` tool rather than a Python state machine. Use CDDL when you
  have a completed spec/plan and want its scripted, resumable, dual-gate contract; use
  devpanel for everything else that benefits from a develop → critique → refactor loop.
- **`parallel_agent.py`** is cross-model consensus verification (Gemini/Cursor/Codex/
  Antigravity agreeing on one artifact). devpanel is single-model (Claude Code
  subagents), role-based adversarial gating — a different axis, not a substitute.
