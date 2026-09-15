# OMP Sub-Agent Dispatch

The parent submits all ready independent units in one OMP `task` call, in waves of at most 32. Use `scout` for
read-only exploration, `reviewer` for quality review, `security-reviewer` for security review, `sonic` only for
mechanical work, and omit `agent` for default implementation work. Children execute directly and never redispatch;
`hub` only coordinates or waits; the parent validates and aggregates evidence. If `task` is unavailable, work inline
and report `DEGRADED`.
