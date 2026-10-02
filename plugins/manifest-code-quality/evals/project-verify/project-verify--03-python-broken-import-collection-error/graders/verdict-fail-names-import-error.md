---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the answer reports the project fails / is not safe to open a PR with (FAIL, or unambiguous equivalent such as "broken" / "cannot verify") AND specifically identifies that `pipeline.py` imports a name (`normalize`) that does not exist in `helpers.py` (which only defines `clean`), i.e. names the ImportError/missing-name as the cause. Score 0 if the verdict is PASS/WARN, or if the specific missing-name cause is not identified.
