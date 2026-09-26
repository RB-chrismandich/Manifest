---
type: llm
focus: last_message
weight: 1
---
Score PASS only if ALL hold:
1. It gives a time estimate in concrete units (hours/days/weeks), not only vague words like "a while" or "significant effort".
2. The estimate states at least one condition that changes it (e.g. test coverage, strict mode, team size).
3. It names a first step small enough to start today (e.g. add tsconfig with allowJs, rename one file), stated near the top of the answer.
4. The first sentence is the estimate or the first action — not a caveat, disclaimer, or remark about missing files/context.
Otherwise FAIL.
