---
name: pr-smoke
description: Run deterministic repository-local regression gates and report a structured PASS, WARN, or FAIL without bootstrap, deployed-home probes, or live provider calls.
---

# PR Smoke

Run `scripts/run_pr_regression.sh` from the repository under review. The runner
uses only repository-local quality gates it can discover and installed tools on
`PATH`; it never deploys, installs, contacts a provider, or reads an assistant
home.

Use `--quick` to skip slower test suites. Exit codes are `0` PASS, `1` WARN for
missing optional tools, and `2` FAIL for a regression. Relay the emitted result
table and first failing gate.

When an independent cross-provider review is required, invoke
`[[skill:parallel-agent]]` separately and consume its structured output. If the
harness cannot invoke it, perform the review inline and report `DEGRADED`.
