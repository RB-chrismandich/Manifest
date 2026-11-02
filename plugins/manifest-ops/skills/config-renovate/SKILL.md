---
name: config-renovate
description: Create, audit, or repair Renovate dependency-update configuration with a seven-day release cooldown and maximum consolidation into one routine PR, including major updates. Use for renovate.json, JSON5, package.json renovate settings, shared presets, or Renovate grouping and release-age troubleshooting.
---

# Renovate configuration

Configure the requested repository or shared preset using
[assets/renovate.json](assets/renovate.json) as a strict starting point.
N-7 means each routine release is at least seven days old, not seven versions
behind or one run per week. Maximize grouping across managers, including majors.
Security fixes are approved immediate exceptions outside the routine group and
PR cap; keep alerts enabled and all merges manual. No further approval is needed
for this exception unless the target has a conflicting policy.

## Workflow

1. Inspect the active configuration and resolved presets, manifests, lockfiles,
   datasource timestamp support, and CI. Edit the active file using Renovate's
   configuration-file precedence. Preserve immutable pins, custom managers,
   registries, allowed-version/ignore constraints, schedules, and unrelated work.
2. Set `minimumReleaseAge: "7 days"`,
   `minimumReleaseAgeBuffer: null` (no extra buffer),
   `minimumReleaseAgeBehaviour: "timestamp-required"`, and
   `internalChecksFilter: "strict"` at root and in the final routine catch-all
   package rule. Give that rule one stable `groupName`/`groupSlug` and set
   `separateMajorMinor`, `separateMinorPatch`, `separateMultipleMajor`, and
   `separateMultipleMinor` to false. Retain `prConcurrentLimit: 1` and
   `automerge: false`. A PR cap alone does not group updates.
3. Apply the scope correctly: in a **repository**, place the catch-all after
   inherited/conflicting routine rules and inspect manager/update-type blocks
   and branch-splitting overrides. In a **shared preset**, consumers can override
   its rules. Validate a representative consuming configuration, report conflicts,
   and never claim a preset universally enforces its policy. Consult
   [precedence details](references/policy.md#precedence-and-scope) for conflicts.
4. Reconcile exceptions using only the relevant reference section:
   [age gaps and scoped recovery](references/policy.md#age-gaps-and-recovery)
   for pins, digests, replacements, rollbacks, or transitive cooldowns;
   [security and maintenance](references/policy.md#security-and-maintenance)
   for alerts or standalone maintenance. The strict starter holds age-unsupported
   routine types and conditional `pinDigest`, and disables standalone maintenance.
   Disclose controls being disabled in an existing repository before changing them.
   Never relax timestamps/strict checks, shorten aging, force dashboard approval,
   or disable security fixes to obtain fewer PRs.
5. Run the target version's `renovate-config-validator --strict --no-global <path>`;
   for package.json settings use supported discovery from the target root.
   Validate shared presets **and** a representative consumer. Prefer an existing
   pinned runner; otherwise verify the official version/runtime before installing.
   Inspect effective outcomes with isolated behavioral fixtures or an authorized
   read-only dry run. See [validation](references/policy.md#validation-and-sources)
   for commands and evidence limits; schema validity alone proves no behavior.

## Completion evidence

Report edited paths, runner/runtime versions, exact validation results, and observed
versus unverified behavior: six-day held, seven-day eligible, missing timestamp
held, and eligible major/minor/patch updates sharing a branch across managers.
For presets, report consumer overrides; for security, verify immediate remediation,
separate grouping, cap bypass, and automerge off, including interactions with
routine `enabled: false` rules. Name blocked datasources and remaining conflicts.
Do not promise one PR across security, maintenance, or multiple base branches.

Write only within the requested scope. Installing a hosted app, changing credentials
or branch protection, deployment, commits, pushes, and publication require separate
authorization. Dry runs can execute package managers: use disposable workspaces.
