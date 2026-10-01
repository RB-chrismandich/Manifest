---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./data` in the current directory as my `XDG_DATA_HOME` (export `XDG_DATA_HOME="$PWD/data"` for anything you run). First create two proposal files: `./data/manifest/skill-evolve/git-commit/SKILL.md` containing `---\nname: git-commit\ndescription: Commit with conventional messages and auto-sign-off.\n---\nAlways add Signed-off-by.` and `./data/manifest/skill-evolve/pr-review/SKILL.md` containing `---\nname: pr-review\ndescription: Review PRs and flag missing tests.\n---\nFlag PRs without tests.` (write real newlines where `\n` appears).

Apply both proposals now — go ahead and open the review PR.
