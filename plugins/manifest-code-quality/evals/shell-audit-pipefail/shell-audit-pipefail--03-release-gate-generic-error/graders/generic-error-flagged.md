---
type: llm
weight: 1
---
Score 1 only if the answer flags that both the `version` and `channel` guards use the identical generic message "Error: something went wrong", which doesn't say which field or step failed, and recommends distinct, descriptive error text that names the failing step (e.g. mentioning `.version` or `.channel` and/or `release.json`). Score 0 if it doesn't call out that the two messages are generic/indistinguishable, or if it doesn't propose naming the failing step.
