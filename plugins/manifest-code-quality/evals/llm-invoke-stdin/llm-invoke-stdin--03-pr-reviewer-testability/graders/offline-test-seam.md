---
type: llm
weight: 1
---
Score 1 only if the answer explains how to test `review_pr_description` in CI without hitting the real gemini CLI or network — by making `REVIEWER_CLI` overridable (e.g. via an environment variable with a default, `os.environ.get("REVIEWER_CLI", "gemini")`) or by injecting a runner, and substituting a stub/fake executable or mock in tests through that seam. Score 0 if the answer does not describe a concrete way to substitute a stub for the real CLI in tests.
