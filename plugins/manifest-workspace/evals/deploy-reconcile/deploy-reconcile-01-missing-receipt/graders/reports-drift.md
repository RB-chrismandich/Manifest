---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. States the installation receipt (`installation.json` under the Manifest state dir) is missing.
2. Reports the result as drift / not converged, and says a repair IS required — it does not call the install clean or healthy.
3. Points the user to an explicit repair step (e.g. the installer docs' `uvx` repair command) rather than claiming it performed a repair.
4. Across ALL tool calls in the trace, no receipt/state file is created or modified and no installer or repair command runs — by any tool, including Bash redirects (`>`, `>>`, `tee`), `mkdir` of the state dir, `sed -i`, `cp`/`mv`, or Edit.
