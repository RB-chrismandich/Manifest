---
type: llm
focus: last_message
weight: 1
---
Score PASS only if ALL hold:
1. The first line/sentence is a concrete action the reader can do now (a code change, a command, or an edit to a named file) — not context, restating the problem, or "The issue is...".
2. The proposed fix actually addresses the missing `users` prop (default it in the component and/or pass `users` in the test). Explicitly explaining the cause is NOT required.
3. The final line names ONE specific next action (e.g. rerun the test) rather than a generic offer of more help.
Otherwise FAIL.
