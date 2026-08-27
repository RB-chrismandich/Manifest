---
name: pr-smoke
description: Run deterministic repository-local regression gates and report a structured PASS, WARN, or FAIL without bootstrap, deployed-home probes, or live provider calls.
---

# PR Smoke

Run `scripts/run_pr_regression.sh` from the repository under review. The runner
uses only repository-local quality gates it can discover and installed tools on
`PATH`; it never deploys, installs, contacts a provider, or reads an assistant
home.

Its full mode mirrors the portable, plugin-safe CI gates: ShellCheck, repository
lint guards, YAML and Markdown validation, command-guide drift, shell syntax,
Bats, and pytest. Bootstrap validation and Lite smoke execution remain CI and
coordinator gates because a released bundle cannot depend on either runtime.
Tools that are not installed produce `WARN`; a gate that runs and fails produces
`FAIL`.

Use `--quick` to skip slower test suites. Exit codes are `0` PASS, `1` WARN for
missing optional tools, and `2` FAIL for a regression. Relay the emitted result
table and first failing gate.

When an independent cross-provider review is required, invoke
`manifest-workspace:parallel-agent` separately and consume its structured output. If the
harness cannot invoke it, perform the review inline and report `DEGRADED`.
