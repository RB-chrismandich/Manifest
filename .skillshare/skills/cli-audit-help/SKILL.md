---
name: cli-audit-help
description: Use when adding or auditing --help/--version on a script or CLI — the help path must succeed before any config/state/dependency lookup, verified in a clean environment (empty HOME, fresh clone, CI), not just a pre-configured machine.
---
# Make --help Work Before Any Dependency Check

The classic invisible-locally / red-in-CI failure: help dies on a fresh clone because a required file or env var is
resolved at the top of the script, before args are parsed.

1. **Spot the failure mode.** A script resolves state at top level — locating a required config file, asserting an env
   var, connecting to a service — and exits nonzero *before* parsing args. `script --help` then fails for anyone lacking
   that state (fresh clone, CI, new contributor) while passing for you because your `~/.config`/HOME is set up.
2. **Reorder the entry point.** Handle `-h|--help|--version` and the `help` subcommand FIRST — before, or as an explicit
   early branch within, the dependency/state resolution block.
3. **Use correct streams and codes.** Help/usage on request → stdout, exit 0. Usage-on-bad-input and errors → stderr,
   nonzero. Keep added help concise.
4. **Verify in a stripped environment, not your configured one.** `env HOME=/tmp/empty-$$ bash ./script --help; echo $?`
   and also from a different CWD. A pass with your real HOME is not evidence.
5. **Pin it with a coverage test.** A test that runs every user-facing entry point's `--help` and asserts exit 0 + a
   `Usage` line on stdout — ideally under the same bare-env conditions CI uses. This is exactly the bug that only CI
   catches.
6. **Document exemptions.** Internal helpers and non-user-invoked hook wrappers can be exempt — list them with rationale
   so the coverage test skips them deliberately, not silently.
