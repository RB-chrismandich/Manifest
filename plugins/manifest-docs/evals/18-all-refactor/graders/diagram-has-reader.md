---
type: regex
target: {source: file, path: docs/ARCHITECTURE_DIAGRAMS.md}
match: contains
flags: i
---
```mermaid(?:(?!```)[\s\S])*reader(?:(?!```)[\s\S])*```
