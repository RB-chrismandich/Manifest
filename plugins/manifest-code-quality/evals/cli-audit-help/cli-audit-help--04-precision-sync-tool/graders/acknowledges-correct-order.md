---
type: llm
weight: 1
---
Score 1 only if the answer confirms that `-h`/`--help` is already handled by the `case` block BEFORE the `SYNC_TOKEN` check and before `src`/`dest` are required, i.e. no reordering is needed, without inventing an ordering bug. Score 0 if it claims help is checked after the env/config requirements, or invents such an issue.
