---
type: llm
weight: 1
---
Score 1 only if the answer recommends (a) piping the Sentry export content into `agy -p` via stdin rather than passing it as a command-line argument, keeping only a short fixed instruction on argv, AND (b) putting the CLI invocation behind a named, injectable seam (e.g. an `AGY_CLI` environment variable with a default, or a wrapper function) so CI tests can substitute a stub instead of the real `agy` CLI/network. Score 0 if either the stdin recommendation or the injectable-seam recommendation is missing.
