---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Write, Edit, Read, Grep, Glob, "Bash(mkdir:*)", "Bash(ln:*)"]
runs: 3
---
I already started a Go module here — save the file below as `go.mod` exactly as given, then scaffold the lint config, Makefile, and a placeholder test for it. The project is named `tinycalc`.

`go.mod`:
```
module tinycalc

go 1.21
```
