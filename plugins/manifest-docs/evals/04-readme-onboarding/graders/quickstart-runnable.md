---
type: llm
focus: {source: file, path: README.md}
---
A new hire reading top to bottom meets, in this order, an install step (`make install` or `pip install -e .`), then `tally ingest <csv>`, then `tally report` — in one code block or in consecutive sections (e.g. an Install section followed by a Quick start); creating a sample CSV first is fine. It names the CSV columns `event,ts` somewhere, and invents no step absent from the code (no docker, no PyPI install, no env vars besides optional proxy). Pass only if all hold.
