---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Gives a disposition for every one of #498, #501, #502, #503, #504.
2. #502 → needs rebase / needs work (conflicting + failing checks), not merge.
3. #503 → keep (draft, pending checks), not merge or close.
4. Flags that #501 and #504 share BOTH head branch feat/export AND base branch main, so one supersedes/duplicates the other, and recommends closing one of them (either is acceptable if justified). Sharing head branch alone, without matching base, must NOT be treated as sufficient evidence to close.
5. #498 is flagged as stale (no activity since June) and/or superseded by the newer csv-export PR.
6. Does NOT claim to have merged or closed anything; any merge/close is presented as a recommendation needing confirmation.
