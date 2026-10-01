---
type: regex
target: {source: file, path: README.md}
match: contains
---
\]\((?:\./)?docs/(?:README|index)\.md\)|^(?=[\s\S]*\]\((?:\./)?docs/GETTING_STARTED\.md[)#])(?=[\s\S]*\]\((?:\./)?docs/CONFIGURATION\.md[)#])
