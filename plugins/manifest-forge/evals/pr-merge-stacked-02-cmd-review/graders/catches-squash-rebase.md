---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Does NOT claim `--delete-branch` on 41 closes PR 42. It says (or is consistent with) GitHub retargeting 42 to main
   when the merged parent branch is deleted.
2. Flags the real problem with `--squash`: 42 still contains 41's original commits, which are not in main after a
   squash, so 42 shows them again / conflicts; recommends rebasing 42 onto main to drop them
   (e.g. `git rebase --onto origin/main <old-41-head-sha> <42-branch>` + `git push --force-with-lease`) — or
   switching to merge commits.
3. Recommends verifying 42's base actually became main before merging it (and retargeting by hand if not), and
   makes sure CI actually runs against the new base after the retarget (e.g. adds `edited` to the workflow's
   pull_request types, pushes/rebases the child, or closes+reopens it) and waits for that run to go green before
   merging; it must not assume the retarget alone re-runs CI.
Fail if the answer says the plan is fine as written, or says the main risk is PR 42 being closed.
