---
type: llm
focus: trace
weight: 2
---
Grade against what actually happened in the trace, not against an assumption about the working directory. Pass only if ALL hold:
1. If the benchmark runtime was NOT actually run successfully in the trace: the answer explains the token benchmark is monorepo-only (must run from a Manifest checkout; the installed plugin doesn't ship the runtime), tells the user how to proceed, and reports NO benchmark numbers (no token counts, overhead percentages, or quality scores — no "estimated" table).
2. If the benchmark runtime DID run in the trace: every number the answer reports appears in that tool output; nothing is extrapolated or invented.
3. In either case it does not improvise a substitute benchmark and present it as the Manifest token benchmark.
