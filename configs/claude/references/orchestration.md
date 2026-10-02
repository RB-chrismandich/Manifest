# Orchestration Reference

> OMP-native task batching, coordination, and parent validation. Referenced from
> `CLAUDE.md`.

## Dispatch workflow

1. Split only genuinely independent work into bounded units.
2. Dispatch every ready unit in one OMP `task` call, using waves of at most 32.
3. Use `scout` for read-only exploration, `reviewer` for quality review,
   `security-reviewer` for security review, `sonic` only for mechanical work,
   and omit `agent` for default implementation work.
4. Each child completes its assigned unit directly and never redispatches.
5. Use `hub` only to coordinate or wait for those children.
6. The parent validates evidence, resolves disagreements, and aggregates the
   result; it does not treat textual overlap as consensus.

When `task` is unavailable, execute the work inline and report `DEGRADED`.
Never invoke a provider CLI as an interactive fallback.

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
