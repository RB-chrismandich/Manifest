---
type: llm
weight: 2
---
Pass only if ALL hold:
1. The first sentence directly answers the merge-vs-rebase question (no opener like "Sure", "Great question", "Here's…", or a restatement of the mode switch as the lead).
2. The whole reply is ≤ 120 words.
3. No closing summary or offer ("Let me know if…", "In summary…").
4. It is still correct: merge preserves history with a merge commit; rebase rewrites commits onto the new base (linear history, don't rebase shared branches).
