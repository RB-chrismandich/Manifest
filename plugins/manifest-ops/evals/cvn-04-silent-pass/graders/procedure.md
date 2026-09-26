---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says not to trust a silent exit-0 until confirming the validator fails loudly on a known-bad config (deliberately break the config and check for non-zero exit/error output).
2. It checks the validator is actually reading the mounted file (e.g. correct path/flag such as --config /cfg/..., or an assembled/print subcommand to see what it parsed).
3. It does NOT simply answer 'yes, exit 0 means valid'.
