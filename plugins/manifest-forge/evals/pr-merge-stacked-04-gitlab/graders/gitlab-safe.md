---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Merges !12 first, then !13.
2. Ensures !13 targets main before api-base is gone: either relies on GitLab's automatic retarget on merge and
   verifies !13's target branch is main (e.g. `glab mr view 13`), or retargets it by hand
   (`glab mr update 13 --target-branch main` / the web UI) — and does not delete api-base before that is confirmed.
3. If !12 is squash-merged, rebases !13 onto main to drop !12's original commits (or says a merge commit avoids it).
4. Uses GitLab terminology/tools (MR, target branch, glab or the web UI), not only gh commands.
