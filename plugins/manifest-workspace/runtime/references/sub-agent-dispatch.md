# Native Sub-Agent Dispatch

Use the current host's supported native mechanism. OMP parents submit all ready
independent units in one `task` call, supervise results, validate evidence, and
aggregate findings. Each task states its bounded unit, acceptance criteria, and
read/write scope. Claude Code parents use only native Agent types actually
discovered from installed plugins; do not infer aliases, model overrides, or OMP
role mappings. This portable reference does not define a second orchestration
implementation. The deployed host's shared dispatch contract is authoritative
for child limits, the narrow delegate-runner exception, and `DEGRADED` behavior.
