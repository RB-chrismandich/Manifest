---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
runs: 3
---
Ugh. I closed my parent PR #87 on GitHub without merging it (we dropped that approach) and then deleted its branch feat-parser with `git push origin --delete feat-parser`. Now the child PR #88, which was based on feat-parser, shows as Closed and the Reopen button is greyed out. #88's own change is still wanted. How do I get #88 back and merged into main?
