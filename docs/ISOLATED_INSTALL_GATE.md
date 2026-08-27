# Isolated single-bundle install gate

Pre-release check that a bundle installs **alone** and brings nothing with it.
Implements §4 1.4 "Isolated single-bundle install gate" of
`docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md`.

## Run it

```bash
python3 tools/isolated_install_gate.py --bundle manifest-docs --json
```

Exit codes, and the distinction matters:

| code | state | meaning |
|---|---|---|
| 0 | `OK` | installed alone, closure clean, uninstall clean |
| 1 | `FAILED` | at least one finding, listed in the report |
| 2 | `UNVERIFIABLE` | could not run — **never** a pass |

`UNVERIFIABLE` exists because the spec's whole premise is that *"a skip that
renders as a pass is the false green this phase exists to remove"*. A missing
`claude` CLI reports 2, not 0.

## Why it is local, not CI

The spec requires a **real** `claude plugin install`; fixture simulation is
disqualified by its own Cursor argument — a gate that only indexes a marketplace
proves nothing about what the harness loads. A real install needs headless auth,
a sandboxed HOME and marketplace network access, none of which CI has today, so
CI wiring stays deferred as R10 rather than silently assumed.

`HOME` is redirected to a scratch directory for the probe, so a real
`--scope user` install cannot touch your own `~/.claude`.

## What it asserts

1. The bundle installs from a local marketplace checkout.
2. No **undeclared sibling bundle** arrives with it — the closure is the bundle
   plus anything it declares.
3. Uninstall clears the **registration**.
4. No non-cache state naming the bundle survives uninstall.

Point 3 is deliberately about the registration, not the filesystem.
`plugin uninstall` retains `plugins/cache/<marketplace>/` and
`plugins/marketplaces/` on purpose — shared marketplace material kept for
reinstall. Measured rather than assumed: after uninstall
`installed_plugins.json` goes to `[]` while the cache directory remains. An
earlier tree-diff version of this check reported 35 surviving paths, all of them
cache — exactly the confident false finding a pre-release gate must not produce.

## Baseline

All eight domain bundles pass as of 2026-08-26:

```text
manifest-code-quality   OK      manifest-security       OK
manifest-docs           OK      manifest-spec-planning  OK
manifest-forge          OK      manifest-workspace      OK
manifest-ops            OK      stitch-design           OK
```

Note what a pass does **not** mean. `token-benchmark` ships a body that invokes
`tests/token_benchmark/harness.py`, a repo-root path absent from the installed
bundle, and `manifest-workspace` still passes here — this gate proves the
*install closure* is clean, not that every skill body's citations resolve. That
is the bundle-local link checker's job, and it currently holds 8 baselined
entries for that skill.
