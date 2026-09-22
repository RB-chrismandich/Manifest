# Orchestration Reference

> Current-host native task batching, coordination, and parent validation.
> Referenced from `CLAUDE.md`.

## Dispatch workflow

1. Split only genuinely independent work into bounded units.
2. On OMP, dispatch every ready unit in one `task` call and use `hub` to
   coordinate. On Claude Code, use its discovered native Agent mechanism and
   native background collection; use no guessed agent name.
3. OMP selects documented specialist roles; Claude uses only discovered agent
   types.
4. Apply the [shared dispatch contract](sub-agent-dispatch.md) for child
   limits, the delegate-runner exception, and unavailable-native behavior.
5. The parent validates evidence, resolves disagreements, and aggregates the
   result; it does not treat textual overlap or vote percentages as consensus.

## Independent-review escalation

Use one capable reviewing agent by default. Add independent review only for a
trust-boundary change, destructive behavior, broad compatibility or deployment
change, conflicting evidence or unresolved uncertainty, or a codebase-wide
investigation with genuinely independent tracks. File, package, module,
language, keyword, and independent-unit counts never trigger independent
review. Workload decomposition is separate: split genuinely independent work
when it reduces latency, while keeping one writer for each mutable file set.

The parent assigns bounded reviewer lenses, validates findings against the
source, and keeps mutation sequential after review.

## Example

```text
Parent:
  task([{ reviewer: security lens }, { reviewer: compatibility lens }])
  hub: wait for both workers
  validate each finding against the change
  aggregate evidence and report the outcome
```
