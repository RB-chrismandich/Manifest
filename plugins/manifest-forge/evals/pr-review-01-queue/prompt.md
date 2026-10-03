---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Here's `gh pr list --state open --json ...` for our repo (today is 2026-09-26). Review every open PR and tell me what to do with each.

```json
[
 {"number":501,"title":"feat: csv export","headRefName":"feat/export","baseRefName":"main","isDraft":false,"mergeable":"MERGEABLE","checks":"SUCCESS","updatedAt":"2026-09-25"},
 {"number":502,"title":"fix: flaky auth test","headRefName":"fix/auth-flake","baseRefName":"main","isDraft":false,"mergeable":"CONFLICTING","checks":"FAILURE","updatedAt":"2026-09-20"},
 {"number":503,"title":"wip: graphql gateway","headRefName":"spike/gql","baseRefName":"main","isDraft":true,"mergeable":"MERGEABLE","checks":"PENDING","updatedAt":"2026-09-24"},
 {"number":498,"title":"feat: csv export (first try)","headRefName":"feat/export-old","baseRefName":"main","isDraft":false,"mergeable":"MERGEABLE","checks":"SUCCESS","updatedAt":"2026-06-01"},
 {"number":504,"title":"feat: csv export v2","headRefName":"feat/export","baseRefName":"main","isDraft":false,"mergeable":"MERGEABLE","checks":"SUCCESS","updatedAt":"2026-09-26"}
]
```

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
