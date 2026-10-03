---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Gives a disposition for every one of #498, #501, #502, #503, #504.
2. #502 → needs rebase / needs work (conflicting + failing checks), not merge.
3. #503 → keep (draft, pending checks), not merge or close.
4. Flags that #501 and #504 have the same owner-qualified head (alice:feat/export) AND the same base (main), plus explicit supersession evidence (#504's body says it supersedes #501), so one duplicates/supersedes the other, and recommends closing one of them (either is acceptable if justified). Sharing head branch name alone — without matching base AND matching head owner — must NOT be treated as sufficient evidence to close.
5. #498 is flagged as stale (no activity since June) and/or superseded by the newer csv-export PR.
6. Does NOT claim to have merged or closed anything; any merge/close is presented as a recommendation needing confirmation.
