---
name: project-verify
description: Use for honest, read-only project quality verification before merge, shipping, or as a PR gate. Selects project-supported checks and reports pass, fail, unavailable, and not-run distinctly; installs nothing.
---

# Project Verification

Run the requested quality checks read-only. Do not install packages, modify
project files, configure global tools, bypass hooks, or claim evidence you did
not observe.

## 1. Discover the project's actual contract first

Before generic language defaults, inspect the target repository's committed
instructions (`AGENTS.md`, `CLAUDE.md`, contribution/testing guides), package and
tool configuration, CI workflows, supported interpreter/container, and relevant
contract checks. Determine the requested target revision and whether the working
tree or staged diff changes an integration boundary. For integration-sensitive
changes, inspect only the relevant producer, consumer, target revision, and
release control; do not turn this into a full repository audit.

Use the repository's documented, isolated/container validation route when one
exists. Otherwise use the exact project-supported local commands only when their
runtime and dependencies are already available. Do not bootstrap, install, or
silently substitute generic commands. If the project contract cannot be
established, report that limitation before selecting checks.

## 2. Select and run checks

Build the check set from the project's committed instructions and CI contract.
Language defaults below are fallback discovery hints only, never a replacement
for project-specific commands:

| Language | Possible checks (only if project-supported) |
|----------|----------------------------------------------|
| Python | configured lint and the documented `pytest`/project test command |
| Go | configured lint and `go test` targets |
| Node | configured package-manager scripts and lockfile-preserving commands |
| Terraform | configured validation, formatting, and security checks |

Before each check, establish its exact command, supported runtime, required
dependencies, and target scope. Record actual command, exit status, and whether
it executed tests/checks. A missing dependency, incompatible runtime, skipped
check, tool-start failure, or zero tests executed is `unavailable` or
`not-run`, never `pass`. Do not prescribe `--no-verify`, `-n`, or another hook
bypass to work around an environment mismatch. Do not report an unexecuted
security scan as a security pass.

Independent checks may run in parallel only when each process has a separately
captured exit status and output. Guard shell sequences with `set -euo pipefail`
or explicit status capture that cannot hide failure. Do not use an unguarded
`wait` or pipeline that returns a later command's status in place of a check's.
Use the repository's configured timeout; classify a timeout as failure or
unavailable according to the tool's observed outcome, never success.

### GitLab connector and CLI recovery

A connector/API 404 establishes only that the connector route did not retrieve
the resource; it does not prove the user lacks access or that the resource is
absent. If the user has independently authenticated `glab` access and current
authorization permits the requested read, use the documented CLI route to
discover or verify the target. Record which route produced the evidence and
what it establishes. Do not use route fallback to bypass managed access
controls, authentication requirements, or action authorization. A CLI login
alone is not evidence of permission for every project or operation.

## 3. Classify evidence

| Outcome | Meaning |
|---------|---------|
| `pass` | The supported check executed successfully and its expected work was observed. |
| `fail` | The check executed and reported a failing result, or timed out. |
| `unavailable` | Required runtime, dependency, access, or tool capability was unavailable. |
| `not-run` | The check was skipped, had zero executions, or was not selected. |

Keep unavailable and not-run distinct from a passing result. A missing tool is
not a warning-shaped pass; state the unmet prerequisite without installing it.
For test checks, report observed passed/failed counts and explicitly say when
the runner reports zero collected/executed tests or does not expose counts.
For integration/release evidence, bind CI or pipeline results to the exact
target/source revision and environment; older or unrelated evidence is stale.

## 4. Report

Return:

- **Result:** overall status, with pass/fail/unavailable/not-run counts.
- **Affected resources:** repository, revision, paths, and integrations checked.
- **Evidence:** each command, runtime, exit status, observed test/check count,
  and relevant CI/release-control evidence.
- **Verification limit:** unavailable prerequisites, skipped checks, zero
  execution, access limits, and unsupported conclusions.
- **Unresolved decision:** only a decision that remains necessary; do not demand
  a human next action when already-authorized work can continue.

The overall result is `PASS` only when every required check actually ran and
passed. Any required failure yields `FAIL`; any required unavailable or not-run
check makes the result incomplete, not green. Optional unselected checks remain
not-run and must not be represented as verified.

## Learning Capture (Optional)

After reporting, a failed check may be recorded with the existing learning-capture
workflow. This is non-blocking and must not change the verification outcome.
