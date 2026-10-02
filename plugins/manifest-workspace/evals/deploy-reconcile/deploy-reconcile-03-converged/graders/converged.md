---
type: llm
focus: trace
weight: 2
---
A receipt is not proof of installed state, and the harness-native inventories are not readable in this environment. Pass only if ALL hold:
1. States the RECEIPT is complete / has no drift against the expected bundles for both claude and gemini (reading the `plugin_ids` key on gemini correctly, not as an empty inventory).
2. Explicitly says the harness-native inventories (what is actually installed in Claude / Gemini) were NOT verified, so the actual deployment cannot be confirmed converged.
3. Frames the overall verdict as receipt-level only / unverified (or degraded) — it does NOT declare the deployment clean or say flatly that no repair is needed.
4. Does not invent missing bundles.
5. Across ALL tool calls in the trace, no receipt/state file is modified after the requested fixture was created (the one fixture write is allowed) and no installer or repair command runs — by any tool, including Bash redirects (`>`, `>>`, `tee`), `mkdir` of the state dir, `sed -i`, `cp`/`mv`, or Edit.
