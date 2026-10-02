---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says the likely cause is that CI invokes yamllint differently from local runs — e.g. a preset `-d relaxed`/`-d default` that ignores `.yamllint`, an inline config, or running without finding the repo config.
2. It asks for, or tells the user to inspect, the CI workflow's lint step and compare it to the committed `.yamllint`.
3. It does NOT simply tell the user to shorten their lines.
