---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer treats the difference between local and CI yamllint invocation/configuration as the likely issue, asks the user to inspect the workflow lint command alongside the committed `.yamllint`, and avoids prescribing shorter YAML lines as the whole solution. It may cite an explicit preset, inline config, or a failure to discover the repository config as plausible causes.
