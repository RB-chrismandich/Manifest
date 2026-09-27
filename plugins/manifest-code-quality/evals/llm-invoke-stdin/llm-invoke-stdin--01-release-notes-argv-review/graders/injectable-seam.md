---
type: llm
weight: 1
---
Score 1 only if the answer recommends putting the CLI invocation behind a named, injectable seam — e.g. an env var such as `SUMMARIZER_CLI="${SUMMARIZER_CLI:-claude}"` used in place of the hardcoded `claude`, or an equivalent wrapper function — so tests can substitute a stub. Score 0 if the answer does not mention making the CLI swappable/injectable for tests.
