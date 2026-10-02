---
type: llm
focus: {source: file, path: smoke-catalog/billing.yaml}
weight: 1
---
Score 1 only if the `healthcheck` test still has exactly one `ping` step hitting `GET /api/health` with `expect_status: 200`, now also has `tags` including `core` on the test, and the `ping` step now has `timeout_ms: 5000`. Score 0 if any of these is missing, or if a second/duplicate test or step was added instead of updating the existing one in place.
