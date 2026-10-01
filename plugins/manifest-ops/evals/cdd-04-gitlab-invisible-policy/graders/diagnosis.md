---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It explains the job is injected from outside the project's own CI config, via a group/instance-level compliance framework pipeline execution policy (or the older, deprecated compliance pipelines feature).
2. It tells the user to ask a group Owner/Maintainer to inspect the group's security/compliance policies (e.g. Group > Secure > Policies, or compliance frameworks) to find the injected config.
3. It proposes aligning thresholds deliberately (change the policy's lint config via its owners, or adopt its limit in `.eslintrc.json`) rather than rewriting code to 80 columns.
4. It does NOT declare the job's origin unknowable, or blame caching/runner flakiness.
