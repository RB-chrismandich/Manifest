---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(find:*)"]
runs: 3
---
Save the file below as `smoke-catalog/billing.yaml` exactly as given, then update the existing `healthcheck` smoke test for the `billing` app: tag it `core` and give its step a 5000ms timeout. Keep it at the `Lite` tier.

`smoke-catalog/billing.yaml`:
```yaml
version: 1
app: billing
tests:
  - id: healthcheck
    tier: Lite
    steps:
      - name: ping
        type: api
        method: GET
        path: /api/health
        expect_status: 200
```
