---
type: llm
focus: {source: file, path: README.md}
---
The README (1) describes tally as counting CSV events and flagging threshold breaches; (2) shows `tally ingest <file>` and `tally report` (with the optional `--threshold`); (3) gives the threshold default as 5 and mentions `tally.toml`; (4) states Python 3.11+ (tomllib); (5) makes no claim that cannot be traced to pyproject.toml, Makefile, or tally/*.py (a claim explicitly marked TODO is allowed; describing window_minutes as unused / not yet used is accurate, but attributing a future purpose to it is not). Pass only if all five hold.
