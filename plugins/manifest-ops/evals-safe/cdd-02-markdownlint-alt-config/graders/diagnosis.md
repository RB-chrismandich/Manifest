---
type: llm
focus: last_message
weight: 1
---
Pass only when the explanation identifies the workflow's explicit `.github/ml-strict.jsonc` selection as bypassing `.markdownlint.jsonc`, which disables `MD013` and `MD033`. It must attribute the discrepancy to differing configurations, not to Markdown files alone. The remedy must intentionally align the CI config with the repository policy or adopt the stricter policy repository-wide; mass reformatting/removing inline HTML is not an acceptable substitute for diagnosing the mismatch.
