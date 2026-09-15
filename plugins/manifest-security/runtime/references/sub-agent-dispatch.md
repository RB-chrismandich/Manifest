# OMP Sub-Agent Dispatch

OMP `task` and `hub` are the only interactive dispatch contract. The parent submits all ready independent units in one
`task` call, in waves of at most 32. Use `scout` for read-only exploration, `reviewer` for quality review,
`security-reviewer` for security review, `sonic` only for mechanical work, and omit `agent` for default implementation
work.

Children execute one bounded unit directly and never redispatch. Use `hub` only to coordinate or wait. The parent
validates evidence and aggregates results. If `task` is unavailable, work inline and report `DEGRADED`; never use a
provider CLI fallback.
