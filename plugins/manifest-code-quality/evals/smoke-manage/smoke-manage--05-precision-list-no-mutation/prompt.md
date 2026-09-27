---
max_turns: 20
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(find:*)"]
runs: 3
---
Save the file below as `smoke-catalog/billing.yaml` exactly as given, then show me what smoke coverage already exists for the `billing` app. Don't change anything, I just want to know what's there.

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
  - id: create-invoice
    tier: Full
    steps:
      - name: create
        type: api
        method: POST
        path: /api/invoices
        body:
          amount: 100
        expect_status: 201
```
