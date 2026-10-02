---
type: regex
target: {source: file, path: docs/README.md}
match: contains
---
^(?=[\s\S]*\]\((?:\./)?GETTING_STARTED\.md\))(?=[\s\S]*\]\((?:\./)?CONFIGURATION\.md\))(?=[\s\S]*\]\((?:\./)?ingest-howto\.md\))(?=[\s\S]*\]\((?:\./)?ARCHITECTURE\.md\))
