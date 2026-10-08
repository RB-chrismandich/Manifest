---
type: llm
focus: last_message
weight: 1
---
Pass only if the response explains that an absent-from-compiled-config `policy-lint` job can be injected outside this repository, such as by a group/instance pipeline execution policy or the older compliance-pipeline mechanism. It must direct the user to a group Owner/Maintainer to inspect group security/compliance policies or framework settings. It must propose aligning the policy's lint threshold with the repository rule (or deliberately adopting the enforced threshold) and must not dismiss the source as unknowable, flaky, or a reason to rewrite all code to 80 columns.
