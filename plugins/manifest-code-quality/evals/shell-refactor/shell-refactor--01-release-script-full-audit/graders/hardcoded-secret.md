---
type: llm
weight: 1
---
Score 1 only if the answer flags the literal `SLACK_WEBHOOK="https://hooks.slack.com/services/..."` value as a hardcoded secret/credential checked into the script, AND recommends sourcing it from an environment variable, secret manager, or CI secret store instead of a literal in source. Score 0 otherwise.
