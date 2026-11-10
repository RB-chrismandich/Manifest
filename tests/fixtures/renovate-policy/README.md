# Renovate policy integration fixtures

Run from the repository root with the approved runtime already installed:

```sh
RENOVATE_TEST_MODULES=/absolute/path/to/node_modules \
  /absolute/path/to/node-24.11.1 --test tests/fixtures/renovate-policy/behavior.test.mjs
```

`RENOVATE_TEST_MODULES` must contain Renovate **44.199.2** and its installed
dependencies. It defaults to the node_modules containing an npm-installed Node
binary. Both versions are asserted before testing. For an isolated npm cache
installation, this exact-pinned command also supplies the matching Node binary:

```sh
npm exec --yes --package=node@24.11.1 --package=renovate@44.199.2 -- \
  node --test tests/fixtures/renovate-policy/behavior.test.mjs
```

The latter may install packages; use an approved installation environment.
No package runner, download, credential, or live repository is required once
the runtime is installed. A sandbox must permit loopback server listening.
Missing runtime, blocked loopback access, or failing tests means behavioral
verification is incomplete. Do not report it as passing or substitute a simulator.

## What runs

`cases.json` fixes time at **2026-11-01 12:00 UTC** and defines registry metadata,
inherited/consumer presets, and a GitHub-style alert response. The harness loads
the skill's actual starter asset, resolves HTTP and built-in presets with
Renovate's resolver, and calls its repository lookup pipeline. This exercises
real npm/PyPI datasource parsing, release selection, rule application, update
classification, alert detection, flattening, and branch generation.

Held candidates are also passed to Renovate's branch processor, which returns
`pending` without creating a branch. Security and routine branch plans are
passed to Renovate's actual limit checker with an occupied routine PR slot.
Resolved representative consumers are also checked for migrations, errors, and
warnings using the same validator stages as `--strict`. No age, matching, merge,
or grouping algorithm is reimplemented in the harness.

| Fixture | Required observation |
| --- | --- |
| Six days / exactly seven days / absent timestamp | Held / eligible / held; pending candidates cannot create a branch |
| Eligible major, minor, patch across npm and pip | One `renovate/all` branch despite inherited conflicting groups |
| Inherited three-day npm cooldown | Repository and shared baseline restore seven days |
| Later consuming rule | Six-day update becomes eligible in consumer group; demonstrates preset enforcement limit |
| One-hour-old security fix beside eligible routine update | Separate branch, cap bypass, automerge off |
| Disabled routine pin and security range fix | Pin control produces a pin only when explicitly re-enabled; security locked-range patch remains available |
| Later routine patch disable | Routine update suppressed; approved security patch still generated |

The starter clears the default extra 30-minute age buffer to test the exact
seven-day boundary. All inherited rules still pass through the actual resolver.

## Isolation and limits

Before importing Renovate, the harness clears application environment variables
(retaining only Node’s test-runner marker), assigns a
temporary home/cache and working directory, and freezes the clock. HTTP registry
and preset responses come only from a loopback server. Non-loopback sockets are
blocked; other loopback ports are also forbidden. Any denied connection or
unexpected service request fails the
suite. Platform/SCM read methods return controlled alert and branch-existence
responses; no platform writers or package managers are invoked. Cleanup restores
the clock/socket hooks and removes the temporary directory.

These are integration tests against pinned internal APIs, not a hosted dry run
or a paid skill evaluation. They start at the extracted-dependency boundary;
they do not test manager extraction, artifact/lockfile generation, CI, PR writes,
OSV remediation, every datasource, mutable digest publication timestamps, or
versioned pinDigest recovery. Keep these limits in completion reports. A target
with different presets, alert providers, managers, or Renovate versions needs
its own validation. Internal API changes require deliberate fixture updates.
