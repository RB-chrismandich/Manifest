---
type: llm
focus: {source: file, path: smoke-catalog/billing.yaml}
weight: 1
---
Score 1 only if the catalog's `create-and-view-invoice` test has an `api` step that captures an id from the invoice-creation response (a `captures` mapping), AND a `ui` step that references that captured value via `${state.<name>}` and lists it under `needs`. Score 0 if the UI step hardcodes a literal invoice id instead of chaining from the captured value, or if no `captures`/`needs` linkage exists.
