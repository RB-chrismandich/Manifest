---
type: llm
focus: last_message
---
Pass only if ALL hold:
1. Explains that `branches: [main]` restricts pull_request triggers to PRs whose BASE is main, so stacked children (based on other branches) do not run CI.
2. Recommends removing or widening that base-branch filter so every stacked PR is gated.
3. Merge order is bottom-up, and after each parent merges the plan confirms the child's base is now main (GitHub
   retargets it automatically when the merged parent branch is deleted; retarget by hand if it did not). It must not
   claim that deleting a merged parent's branch closes the child.
4. Makes sure CI actually runs against the new base after the retarget (e.g. adds `edited` to the workflow's
   pull_request types, pushes/rebases the child, or closes+reopens it) and waits for that run to go green before
   merging; it must not assume the retarget alone re-runs CI.
