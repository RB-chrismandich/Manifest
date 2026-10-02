# CI Trigger Audit Dispatch

For three or more independent workflow files, audit one workflow per review unit,
then merge the structured findings. Below that threshold, audit inline. Preserve
this workflow-count rule because the workflow files are independently auditable.
If structured output is unavailable, perform the review inline and report
`DEGRADED`.

For this security analysis, submit all ready workflow-audit units in one OMP
`task` call (in waves of at most 32), using `security-reviewer`. Each
dispatched reviewer completes its assigned workflow audit directly and does
not re-dispatch; the parent validates and merges the structured findings. If
`task` is unavailable, perform the review inline and report `DEGRADED`.
