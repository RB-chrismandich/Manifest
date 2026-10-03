---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Classifies #801 as closeable (EMPTY 0-file PR) even though its disposition says merge.
2. #802 → ready to merge; #803 → stale/closeable (no activity since March, beyond 90 days) or flagged for the user to decide.
3. feat/billing and feat/ui-tweak → safe to delete (squash-merged), despite branch_clean reporting nothing merged.
4. feat/proto and old/notes → confirm individually (may hold unmerged work), NOT auto-deleted.
5. Remote deletion (origin/feat/billing) is opt-in, not done by default; main is never deleted.
6. Ends by asking the user to confirm (e.g. reply "apply") before closing or deleting anything; does not claim to have acted.
