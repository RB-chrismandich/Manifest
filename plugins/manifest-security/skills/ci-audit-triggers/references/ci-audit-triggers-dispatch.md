# CI Trigger Audit Dispatch

For three or more independent workflow files, audit one workflow per review unit,
then merge the structured findings. Below that threshold, audit inline. Preserve
this workflow-count rule because the workflow files are independently auditable.
If structured output is unavailable, perform the review inline and report
`DEGRADED`.
