---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
runs: 3
---
Quick sanity check before I go: I have stacked PRs 41 <- 42 <- 43 (42 is based on 41s branch, 43 on 42s). My plan is to run `gh pr merge 41 --squash --delete-branch`, then the same for 42, then 43. Anything wrong with that?
