# Sub-Agent Dispatch and Selection Rules

> Read-on-demand policy packaged with the Spec Planning bundle.

OMP `task` and `hub` are the only interactive dispatch contract. For independent
units, the parent submits every ready unit in one `task` call, in waves of at
most 32. Use `scout` for read-only exploration, `reviewer` for quality review,
`security-reviewer` for security review, `sonic` only for mechanical work, and
omit `agent` for the default implementation worker.

Each child receives one bounded task and performs it directly; children never
redispatch. Use `hub` only to coordinate or wait. The parent validates evidence
and aggregates results rather than inferring consensus from overlapping text.

If `task` is unavailable, complete the work inline and report `DEGRADED`. Never
fall back to a provider CLI for interactive fan-out. Read-only critics do not
edit code; only an assigned implementation worker may write.

Every dispatching skill states its units and threshold, links this guidance, and
records its `subagents` disposition in command policy.
