# Codex Plugin Reconciliation, ADHD Plugin, and Model Policy Design

**Date:** 2026-08-09
**Status:** Approved design

> **Adopted implementation-review amendment:** Amendment 1 corrects the
> assumption that retiring the legacy skill catalog alone resolves Codex's
> startup budget. Rationale:
> `2026-08-09-codex-plugin-reconciliation-SPEC-AMENDMENTS.md` §1.

## Problem

Codex currently reports that its skills context budget has been exceeded. The
observed installation has nine enabled Manifest plugins, while the canonical
marketplace contains eleven. `manifest-delegate` and `manifest-docker` are
missing. Because native plugin coverage is incomplete, bootstrap retains the
full legacy `~/.codex/skills` catalog, creating overlapping discovery paths.

Follow-up inspection with `codex debug prompt-input` showed that overlap is not
the complete cause. After the flat catalog is retired, the native plugin catalog
still contains enough skill names, descriptions, and paths to exceed Codex's
startup limit. Codex limits initial skill metadata to 2% of model context, or
8,000 characters when the context size is unknown. Native convergence therefore
needs a startup-visibility policy in addition to legacy catalog retirement.

The same installation also has the upstream `i-have-adhd` plugin enabled. Its
session-start hook invokes `${CLAUDE_PLUGIN_ROOT}/hooks/always-on.mjs`, a
Claude-specific path contract that is incompatible with Codex and produces a
hook-failure notification.

## Goals

- Make bootstrap install, enable, update, and verify every canonical Manifest
  plugin for Codex.
- Retire the flat Codex skill catalog only after complete native verification.
- Eliminate duplicate skill loading and the resulting skills-context warning.
- Mirror `i-have-adhd` as a pinned, attributed Manifest plugin with always-on
  behavior across all supported harnesses.
- Replace Claude-specific hook assumptions with harness-native delivery.
- Preserve recoverability and avoid deleting unowned third-party state.
- Support ordered, portable model preferences and fallbacks in skill
  frontmatter for Codex, Gemini, Antigravity, and Cursor.
- Let users choose automatic fallback or confirmation before switching models.

## Non-Goals

- Fetching mutable upstream plugin content during bootstrap.
- Generically rewriting arbitrary third-party plugin caches.
- Removing an upstream third-party plugin from the user's machine.
- Refactoring unrelated bootstrap deployment domains.
- Embedding concrete provider model IDs in individual skill files.
- Treating authentication, configuration, safety, output, or task failures as
  reasons to switch models.

## Chosen Approach

Bootstrap will delegate plugin convergence to the existing Manifest deployment
service and harness adapters. It will not duplicate native plugin lifecycle
logic in `bootstrap/lib/deploy.sh` or generate a second filtered skill catalog.

The new `manifest bootstrap-sync` operation will choose initial install, legacy
migration, or receipt-backed reconciliation according to the observed state.
The operation accepts a verified local checkout as its desired source and
returns structured per-harness results to bootstrap.

Generated Codex skill metadata keeps a small, qualified allowlist available for
implicit routing and marks every other Manifest skill explicit-only. This does
not generate a second skill catalog or remove capabilities from plugins; users
can still invoke every installed skill explicitly.

## Architecture

After shared configuration files are deployed, bootstrap invokes the
coordinator for enabled harnesses. For Codex, the coordinator performs these
steps in order:

1. Register or refresh the local `manifest` marketplace.
2. Load the canonical bundle inventory from validated plugin contracts.
3. Inspect Codex's installed and enabled plugin state.
4. Install missing bundles, enable disabled bundles, and update stale local
   installations.
5. Verify every required bundle's version and declared components through the
   Codex adapter.
6. Reconcile the mirrored ADHD plugin and any conflicting upstream installation.
7. Retire the legacy Codex skill catalog only after the complete catalog is
   verified.
8. Re-inspect Codex and persist the final verified ownership receipt.

If convergence fails, the legacy skill catalog remains available. Bootstrap
reports an unsuccessful Codex deployment rather than claiming a false-green
installation or leaving Codex with no skills.

## Components

### Bootstrap Coordinator

The coordinator owns the state transition between initial install, migration,
and reconciliation. Shell code supplies configuration and renders results; it
does not make plugin-by-plugin lifecycle decisions.

The operation is idempotent and receipt-aware. It resumes partially completed
work and distinguishes missing, disabled, stale, incompatible, and unverifiable
plugins in its output.

### Canonical Catalog Reconciler

The reconciler compares validated repository contracts with native marketplace
state. The contracts remain the source of truth for bundle identity, version,
components, and harness compatibility. Adding a canonical bundle to the
marketplace must make the next bootstrap install it automatically.

### Mirrored ADHD Plugin

Manifest will add a canonical plugin named `manifest-i-have-adhd` under
`plugins/`. It will contain the mirrored instruction skill, its always-on hook,
generated harness views, and a provenance record containing:

- Upstream repository URL.
- Exact upstream tag or commit.
- Checksums of mirrored source files.
- Upstream license and attribution.
- Last reviewed synchronization date.

Upstream updates occur only through an explicit reviewed sync process. Bootstrap
never fetches or executes mutable upstream content.

### Harness-Neutral Hook Launcher

The mirrored bundle uses a checked-in launcher that validates its input and
resolves bundled resources without `${CLAUDE_PLUGIN_ROOT}`. Generated or native
plugin views invoke the launcher using the path mechanism supported by each
harness.

The bundle declares, for every supported harness:

- Native hook delivery where the harness supports session-start hooks.
- Generated or imported hook configuration where a safe Manifest adapter exists.
- Harness-native always-loaded guidance where no lifecycle hook exists.

A harness is not reported as fully compatible unless one of these mechanisms
provides the always-on behavior. An unavailable always-on delivery path is a
blocking compatibility error for this bundle, not a silent or degraded success.

Existing capability metadata that incorrectly declares Codex lifecycle hooks
unsupported must be corrected to reflect Codex's demonstrated `SessionStart`,
`Stop`, and `PermissionRequest` hook surfaces.

### Codex Skill Cutover

Codex continues to use the flat Manifest skill catalog until all required native
plugins verify. The final cutover replaces the Manifest-wide symlink with a
Codex skills directory containing only Codex's system skills.

The coordinator records the previous skill-source state so rollback can restore
only the link or directory that Manifest changed.

### Codex Startup Skill Policy

Codex reads `agents/openai.yaml` beside each skill. The plugin-view generator
must emit that file for every repository skill with an explicit
`policy.allow_implicit_invocation` boolean. The qualified allowlist lives in
`configs/claude/config/skill_policies.yml` and contains only:

- `manifest-code-quality:antipattern-detect`
- `manifest-security:code-audit`
- `manifest-workspace:help`

All other Manifest skills use `allow_implicit_invocation: false`. They remain in
their plugin manifests and remain callable through explicit `$bundle:skill`
invocation, but they do not consume the initial model-visible skill list.

Generation fails closed when the allowlist is missing, contains duplicates, or
names a qualified skill absent from the repository. Explicit true and false
metadata is generated for every skill so a policy change cannot leave stale
files behind.

A local marketplace path and plugin version are not sufficient freshness
proof. During prepared reconciliation, if an installed plugin tree hash differs
from the desired tree hash at the same version, the adapter must replay the
marketplace refresh before accepting version-matching rows. This ensures policy
metadata reaches existing installations without requiring artificial version
bumps for generated-view corrections.

### Cross-Harness Model Frontmatter

Skill frontmatter supports an optional `models` map whose keys are canonical
harness names and whose values are ordered portable tier chains:

```yaml
models:
  codex: [advanced, flash, auto]
  gemini: [pro, flash, auto]
  antigravity: [advanced, flash, auto]
  cursor: [advanced, flash, auto]

model_fallback:
  mode: confirm
```

`agy` is accepted as an input alias and normalized to `antigravity`. The schema
remains extensible to Claude and Devin. Concrete GPT, Gemini, Antigravity, and
Cursor model identifiers remain centralized in `parallel_agent.yml`;
`command_config.yml` contains routing references but no duplicate provider IDs.
Skills express capability and cost intent through tiers.

The metadata is optional. A skill without `models` or `model_fallback` keeps the
active harness's configured defaults. Skills declare overrides only when their
quality, latency, capability, or fallback requirements differ from those
defaults, avoiding repetitive frontmatter that would consume the skills budget.

Model fallback mode follows this precedence:

```text
explicit CLI or session choice
    -> skill frontmatter override
    -> global command_config.yml default
```

The global default is `confirm`. Supported modes are:

- `confirm`: explain the classified failure and proposed model change, then
  require approval before retrying. Declining stops the operation.
- `auto`: advance to the next eligible tier and record the reason without
  prompting.

Non-interactive execution never waits for input. It switches models only when
`auto` is explicitly selected by the invocation, skill, or global
configuration. Otherwise it stops with a structured recovery message naming
the next available model.

The resolver advances for unsupported or unavailable models, rate limits,
transient provider failures, capacity exhaustion, quota rejection, and billing
rejection. Authentication failures, invalid configuration, unsafe requests,
malformed output, and task or application errors remain blocking. A harness's
native `auto` selection is the final fallback when the harness supports it.

Generated plugin views validate harness keys and tier names, preserve fallback
order, and translate the selected tier to native model arguments at invocation
time. When a harness cannot change models within the active session, the
dispatcher performs a model-targeted handoff or relaunch using the harness's
native CLI and preserves the task context required by the skill. A generator
omits unsupported native fields rather than emitting an invalid manifest.

## Existing Upstream Plugin Migration

An installed `i-have-adhd@i-have-adhd` plugin conflicts with the canonical
mirrored bundle because both provide the same always-on behavior. The coordinator
uses this sequence:

1. Install and verify `manifest-i-have-adhd@manifest`.
2. Probe its session-start hook successfully.
3. Disable, but do not uninstall, `i-have-adhd@i-have-adhd`.
4. Record its prior enabled state in Manifest's ownership receipt.
5. Continue Codex cutover only after duplicate behavior has been removed.

If the mirrored plugin or hook fails verification, the upstream plugin is left
unchanged. If disabling the upstream plugin fails, reconciliation stops before
the flat skill cutover. Uninstall or rollback restores the upstream enabled
state only when the receipt proves Manifest changed it.

## Error Handling and Recovery

Plugin installation is incremental, while skill cutover is transactional:

- Successfully verified plugins remain installed and are recorded.
- A later bootstrap resumes without reinstalling verified bundles.
- Any required plugin failure keeps the legacy Codex skills source intact.
- Bootstrap reports the failing bundle, sanitized native command result, and a
  concrete recovery command.
- An enabled Codex target with incomplete required convergence makes bootstrap
  exit unsuccessfully.

The runtime ADHD hook is advisory and fail-open. A style-loading failure must
not prevent a harness session from starting. The launcher routes failures to a
bounded Manifest diagnostic record containing plugin, harness, version, and
reason. Repeated identical failures are deduplicated to prevent notification
spam. `manifest reconcile` surfaces the degraded state and attempts repair when
invoked with `--apply`.

All mutations follow receipt-backed ownership rules. Manifest does not delete
unowned third-party plugins or overwrite unrelated user configuration.

## Data Flow

```text
bootstrap deploy
    -> resolve and validate canonical contracts
    -> select install, migration, or reconcile
    -> inspect native marketplace and plugin state
    -> install, enable, or update required bundles
    -> verify versions, components, and hook probe
    -> disable the conflicting upstream ADHD plugin when applicable
    -> retire the flat Codex skill catalog
    -> re-inspect native state
    -> persist the ownership receipt and report
```

## Testing

### Unit and Contract Tests

- Coordinator selection for first install, legacy migration, and reconciliation.
- Missing, disabled, stale, incompatible, and unverifiable plugin states.
- Interrupted reconciliation and idempotent resumption.
- Automatic inclusion of newly added canonical marketplace bundles.
- Hook compatibility declarations for every supported harness.
- Provenance tag or commit, checksums, attribution, and license validation.
- Hook input validation, resource resolution, missing dependencies, bounded
  diagnostics, deduplication, and fail-open behavior.
- Per-harness model-chain parsing and `agy` alias normalization.
- Central tier-to-provider-model resolution without concrete IDs in skill files.
- Preferred-model unavailability, rate-limit, transient, capacity, quota, and
  billing fallback classifications.
- Confirmation acceptance and rejection, explicit automatic fallback, and
  non-interactive refusal when automatic fallback is not authorized.
- Final native `auto` selection, blocking failure classes, and unchanged
  behavior when model metadata is absent.
- In-session model changes where supported and context-preserving native
  handoff or relaunch where they are not.
- Frontmatter budget validation that prevents model metadata from recreating
  the Codex skills-context overflow.
- Deterministic `agents/openai.yaml` generation for every repository skill,
  with exact allowlist and fail-closed policy validation.
- Same-version local plugin content drift forces marketplace refresh before
  prepared reconciliation can verify the target tree hashes.

### Bootstrap and Adapter Integration Tests

- Isolated-home bootstrap invokes the coordinator and propagates structured
  failures instead of reporting success.
- Codex installs and enables every canonical contract.
- The flat skills source remains unchanged after any required verification
  failure.
- The flat skills source becomes system-only after complete verification.
- The upstream ADHD plugin is disabled only after the mirrored plugin and hook
  verify.
- Rollback restores the upstream plugin's prior enabled state and previous
  Codex skill source.

### Native Codex Smoke Test

The native scenario starts with nine enabled Manifest plugins,
`manifest-delegate` and `manifest-docker` missing, the flat legacy skills
symlink, and the incompatible upstream ADHD hook. After bootstrap:

- Every canonical Manifest plugin is installed and enabled.
- `manifest-delegate`, `manifest-docker`, and `manifest-i-have-adhd` are visible.
- `i-have-adhd@i-have-adhd` remains installed but is disabled.
- `~/.codex/skills` exposes only Codex system skills.
- A fresh Codex session emits no skills-context-budget warning.
- `codex debug prompt-input` exposes only the three qualified Manifest implicit
  entry points while explicit-only skills remain installed.
- Session start emits no hook-failure notification.
- A second bootstrap produces no state changes.

## Acceptance Criteria

1. Bootstrap automatically converges Codex to the complete canonical Manifest
   plugin catalog.
2. Newly added canonical plugins require no separate manual Codex install step.
3. Codex never loses the legacy skill fallback before native verification is
   complete.
4. A fresh Codex session does not report that the skills context budget was
   exceeded, and startup prompt inspection shows only the qualified implicit
   allowlist from Manifest plugins.
5. The mirrored ADHD plugin is reproducible, attributed, always-on, and
   represented truthfully across every supported harness.
6. Existing upstream ADHD installations are disabled reversibly after the
   mirrored replacement verifies.
7. Hook failures do not block sessions or generate repeated notifications, and
   remain discoverable through Manifest diagnostics and reconciliation.
8. Repeated bootstrap runs are idempotent.
9. Skill frontmatter can express ordered portable model tiers for Codex,
   Gemini, Antigravity, and Cursor without embedding provider model IDs.
10. Model switching follows the configured confirmation policy and falls back
    only for explicitly classified model or provider failures.
11. Non-interactive runs never prompt or silently switch models without an
    explicit automatic-fallback policy.
