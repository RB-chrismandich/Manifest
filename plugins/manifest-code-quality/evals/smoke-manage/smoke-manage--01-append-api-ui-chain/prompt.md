---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Read, Grep, Glob, "Bash(python3:*)", "Bash(find:*)"]
runs: 3
model: sonnet
---
We just shipped invoice creation and viewing for the `billing` app. Add a `Lite`-tier smoke test named `create-and-view-invoice` that: creates an invoice via `POST /api/invoices` with body `{"amount": 100}` expecting a 201, captures the new invoice's id, then loads `/invoices/<that id>` in the UI to confirm it renders. File it under the `billing` app in the smoke catalog.

This checkout doesn't include the `scripts/smoke.py` orchestrator, so write the catalog entry directly to `smoke-catalog/billing.yaml` (create the file) in the catalog's YAML format.
