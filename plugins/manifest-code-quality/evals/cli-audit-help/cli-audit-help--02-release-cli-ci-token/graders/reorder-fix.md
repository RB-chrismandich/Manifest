---
type: llm
weight: 1
---
Score 1 only if the answer moves the `--help` (ideally also `-h`) handling above the `token_file` existence check, so usage prints before any token/HOME lookup — shown in rewritten code or stated explicitly. The explanation may be brief or implicit in the fix (e.g. "move the --help check above the token-file resolution"). Score 0 if it blames CI infrastructure without changing the order, or leaves the token check ahead of `--help`.
