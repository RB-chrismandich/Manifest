# Conditional policy details

Use the section relevant to the target; the core workflow and completion contract
live in [SKILL.md](../SKILL.md). Sources checked 2026-11-02; runtime fixtures target
Renovate 44.199.2 with Node 24.11.1. Recheck semantics for other versions.

## Precedence and scope

All matching package rules merge in order; later conflicting values win. Root
values alone do not defeat inherited datasource-specific rules. A repository's
final catch-all can reconcile inherited three-day npm cooldowns and monorepo
groups. A shared preset cannot control later consuming repository rules or
later presets. Resolve and validate a representative consumer, inspect its
matching rules and branch plans, and report remaining conflicts explicitly.
Do not rewrite an unrelated consumer or promise universal enforcement.

Inspect manager/update-type blocks and `additionalBranchPrefix`, `branchTopic`,
and nested `group` overrides for splitting. Different base branches need separate
PRs. Maximum grouping deliberately includes majors; if CI fails, identify the
incompatible dependency and propose the smallest exception.

`config:recommended` is a minimal starting point. `config:best-practices` also
introduces standalone maintenance, pinning, and a shorter npm cooldown; reconcile
these rather than assuming the preset satisfies this policy.

Sources: [Package rules](https://docs.renovatebot.com/configuration-options/#packagerules),
[Group all](https://docs.renovatebot.com/presets-group/#groupall),
[Separation](https://docs.renovatebot.com/configuration-options/#separatemajorminor),
[Full presets](https://docs.renovatebot.com/presets-config/).

## Age gaps and recovery

Renovate does not apply release aging to `pin`, `replacement`, `bump`, `rollback`,
or `lockfileUpdate`. Holding them disables useful initial pinning, migrations,
and recovery; it does not remove existing immutable pins. Re-enabling those
unsupported types requires a disclosed policy exception, not a claim that seven
days now applies.

`digest` and `pinDigest` support is conditional. An unversioned `pinDigest`
reference such as `latest` bypasses aging even with required timestamps. Holding
initial digest pinning prolongs floating references: disclose this tradeoff.
For a versioned reference that could safely recover from the starter's hold:

1. Identify its exact manager, datasource, package, file, versioned reference,
   and proposed update type in extraction/lookup logs.
2. Verify the datasource supplies the candidate's usable `releaseTimestamp`.
   Determine whether it dates the version or the changed digest content; a
   version timestamp cannot guarantee that newly pushed content is seven days old.
3. In a disposable fixture or authorized dry run, append a narrowly matched
   `enabled: true` rule for that package/file/manager and `pinDigest` only.
   Retain required timestamps, strict checks, and the full seven-day delay.
4. Verify six-day/missing dates remain held, seven-day dates become eligible,
   existing pins remain intact, and unrelated unversioned references stay held.
   Apply the scoped rule only when this evidence supports it; otherwise report
   the blocked update or obtain an explicit exception.

The starter explicitly clears Renovate 44.199.2’s default 30-minute
`minimumReleaseAgeBuffer` so exactly seven days is eligible. This removes only
the extra buffer, retaining the full seven-day check. Reconcile inherited buffers
when inspecting effective rules.

A newer candidate may be held while an older eligible version is selected.
An unknown timestamp can hold an entire group. Report the blocker; do not make
its timestamp optional. Lockfile-generated transitive versions are selected by
the package manager, outside Renovate's direct dependency filter. Inspect native
package-manager cooldowns if transitive coverage is requested, and name gaps.

Source: [Minimum release age](https://docs.renovatebot.com/key-concepts/minimum-release-age/),
[Age buffer](https://docs.renovatebot.com/configuration-options/#minimumreleaseagebuffer).

## Security and maintenance

The starter's `vulnerabilityAlerts` enables alerts, clears the routine group, and
keeps automerge off. Renovate's alert defaults clear aging and ordinary PR caps.
Do not treat `vulnerabilityAlerts.minimumReleaseAge` as a security cooldown.
Preserve the approved immediate exception without enabling automatic merging or
weakening CI. Test against the actual alert mechanism used by the repository;
GitHub alerts and OSV are different paths, and supported ecosystems vary.

Routine `enabled: false` rules must be checked against security processing, not
assumed harmless. Verify alert detection, fix selection, and final branch planning
with the target's disabled types and range strategy. Report a blocked remediation
and use a narrowly scoped security correction rather than enabling routine types
wholesale. On the pinned GitHub-alert path, the starter's explicit
`vulnerabilityAlerts.enabled: true` supplies a forced enable; fixtures verify
routine pin suppression, a security fix of a locked range, and remediation even
when a later rule disables routine patches. The locked-range fix is classified
as `patch` with `isLockfileUpdate: true`, not `updateType: "lockfileUpdate"`;
matching only that update type is not a universal lockfile filter. Other alert
providers and unsupported update types still require target-specific checks.

Standalone lockfile maintenance is not grouped with normal updates and its aging
is package-manager dependent. Keep it disabled in a fresh baseline; existing
maintenance requires a disclosed exception or conflict resolution. Ordinary
lockfile changes accompanying updates remain. Onboarding/config migrations can
also produce separate PRs.

Sources: [Alerts](https://docs.renovatebot.com/configuration-options/#vulnerabilityalerts),
[Maintenance](https://docs.renovatebot.com/configuration-options/#lockfilemaintenance).

## Validation and sources

Explicit validator filenames default to global configuration unless `--no-global`
is supplied. Use `renovate-config-validator --strict --no-global <path>` with the
same version as the target runner. A failed private-preset fetch is not a pass.
Package.json settings require discovery from the repository root.

The reproducible integration fixtures in `tests/fixtures/renovate-policy/` resolve
presets and run actual Renovate lookup, alert processing, and branch generation
with a fixed clock and controlled services. Their README records how to run them
and what they do not establish. They are repository development tests, not a
requirement to copy a test harness into every consuming repository.

For target-specific evidence, use an authorized disposable `--dry-run=full` run
with debug logs. Distinguish validator success, fixture behavior, and live dry-run
results. Unavailable behavioral verification is incomplete, not success.

Sources: [Validation](https://docs.renovatebot.com/config-validation/),
[Upgrade practices](https://docs.renovatebot.com/upgrade-best-practices/),
[pinned upstream source](https://github.com/renovatebot/renovate/tree/44.199.2/lib/workers/repository).
