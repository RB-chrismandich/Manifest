---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It classifies the gap as a deployer bug (source and docs agree on five; deploy_gemini produces three on every run), citing deploy_gemini / lines ~128-132 as evidence.
2. Its fix changes deploy_gemini to reuse `link_shared_assets "$HOME/.gemini"` rather than hand-adding two more create_symlink calls.
3. It backfills the live environment (relink `skills` and `.plans` now) so a full redeploy isn't required.
4. It recommends a test asserting all five links for Gemini (the full contract).
