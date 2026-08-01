# Bootstrap-Free Cross-Harness Plugin Distribution Design

**Date**: 2026-08-01
**Status**: Approved design; pending written-spec review
**Scope**: Replace Manifest's bootstrap deployment with an ephemeral installer
that imports the nine domain bundles into every supported harness at user scope

---

## 1. Outcome

Manifest will retire `bootstrap.sh` and its home-directory deployment model.
Users will instead run an ephemeral coordinator through `uvx`:

```bash
uvx --from manifest-agent manifest install
```

The coordinator will install all nine domain bundles through each harness's
native plugin or extension mechanism, configure declared capabilities, verify
the effective installation, and exit. The installed bundles will operate
offline without bootstrap, `uvx`, or a permanently installed Manifest runtime.

Full parity means equivalent capabilities, not identical files. Harnesses may
represent skills, agents, hooks, MCP servers, and guidance differently, but no
capability may disappear silently.

## 2. Decisions

### 2.1 Thin ephemeral coordinator

`manifest-agent` is an installation, translation, reconciliation, and removal
tool. It is acquired through `uvx` and is not required during normal agent
sessions.

The coordinator may:

- detect supported harnesses and their versions;
- resolve one consistent Manifest release;
- invoke native plugin and extension managers;
- merge Manifest-owned hooks, MCP servers, rules, and settings;
- verify installed capabilities; and
- record non-secret installation state.

It must not become a replacement home-tree deployer or a runtime dependency of
installed skills.

### 2.2 Nine domain bundles are the capability source

The canonical capability sources are:

1. `manifest-code-quality`
2. `manifest-docs`
3. `manifest-forge`
4. `manifest-graphify`
5. `manifest-ops`
6. `manifest-security`
7. `manifest-spec-planning`
8. `manifest-workspace`
9. `stitch-design`

There will be no `manifest-core` plugin. A core plugin would recreate a
mandatory bootstrap dependency, and cross-plugin runtime resolution is not
portable across the supported harnesses.

`adversarial-design-loop` remains an independent optional plugin and is not one
of the nine domain bundles governed by this parity contract.

### 2.3 One portable contract, generated native views

Each domain bundle will contain one portable capability contract. Harness-native
plugin manifests and configuration views will be generated from that contract.
Generated views are release artifacts, not independently maintained sources.

CI will regenerate every view and fail when committed or packaged output drifts
from its contract.

### 2.4 User-scope parity

All nine bundles will be installed at user scope into every detected supported
harness by default. Repository-specific guidance and permissions remain committed
inside each project.

`--harness` may restrict an operation to an explicit target. `--harness all`
requires every supported harness to be present and treats a missing harness as
a failure. The default detects and configures the supported harnesses already
installed on the machine; it does not install or update the harness CLIs.

### 2.5 Offline operation after installation

Every domain bundle must contain the scripts, assets, references, and other
runtime files its capabilities need. Installed skills must not invoke:

- `bootstrap.sh` or anything under `bootstrap/`;
- `~/.claude/scripts`, `~/.claude/config`, or sibling harness home trees;
- `uvx` or `manifest-agent`; or
- a shared plugin whose files are resolved by cross-plugin path arithmetic.

Bundle-local files resolve relative to the installed plugin root. Cross-domain
behavior uses declared skill or capability interfaces rather than shared home
paths.

## 3. Considered Approaches

### 3.1 Domain contracts plus coordinator union -- selected

Each domain declares its own components and external capabilities. The
coordinator unions and deduplicates those declarations, applies them once per
harness, and verifies the result.

This preserves domain ownership while preventing duplicate MCP servers, hooks,
and settings entries.

### 3.2 Core plugin plus domain plugins -- rejected

A core plugin could hold shared scripts, hooks, MCP declarations, and agents.
This is rejected because dependency installation and cross-plugin file
resolution differ by harness. It would also make every domain depend on a
tenth bundle with no standalone user capability.

### 3.3 Fully autonomous domain installers -- rejected

Allowing each bundle to install all dependencies independently would minimize
coordinator logic but create duplicate registrations, conflicting versions,
unclear uninstall ownership, and inconsistent failure behavior.

## 4. Portable Capability Contract

Each bundle will declare components, external capabilities, compatibility, and
provenance in a schema validated by CI and `manifest-agent`.

Illustrative shape:

```yaml
schema_version: 1
bundle: manifest-forge
version: 0.2.0

components:
  skills: []
  agents: []
  hooks: []
  runtime: []

capabilities:
  mcp:
    default: []
    optional:
      - github
  executables:
    required:
      - git
    optional:
      - gh
      - glab

compatibility:
  claude: native
  codex: native
  gemini: generated
  cursor: generated
  antigravity: imported
  devin: native
```

Capability tiers have fixed semantics:

- `required`: installation is blocked if the capability cannot be provided or
  verified.
- `default`: installed automatically; failure produces an explicit degraded
  result.
- `optional`: installed only through interactive selection or `--with`; never
  inferred merely because a skill could use it.

MCP and executable declarations are explicit. The coordinator must not scan
skill prose and guess dependencies.

Context7 will be declared as a default MCP capability by each domain that uses
it directly. The coordinator will union repeated declarations and register one
user-scope server per harness. GitHub, Sentry, Linear, Atlassian, and other
catalog integrations remain opt-in.

## 5. Harness Adapters

`manifest-agent` will provide one adapter per supported harness. Each adapter
has one responsibility: translate the portable desired state into that
harness's supported native operations and verify the effective result.

| Harness | Native path | Adapter responsibility |
|---|---|---|
| Claude Code | Marketplace and plugins | Register the Manifest marketplace, install bundles, configure supported hooks and MCP |
| Codex | Marketplace snapshots and plugins | Install bundle views, configure Codex-native hooks, MCP, and instructions |
| Gemini CLI | Extensions, skills, hooks, and MCP | Install generated extension views and configure native capabilities |
| Cursor | Plugin marketplace and rules | Install generated plugin views and native rules/configuration |
| Antigravity (`agy`) | Plugin install/import | Import the compatible Claude or Gemini view and verify exposed capabilities |
| Devin | Plugins, rules, skills, and MCP | Install native bundle views and configure Devin-native capabilities |

emdash is not a deployment target. It launches one of these harnesses with the
real user environment and therefore inherits that harness's installation.

Native support is preferred. When a capability cannot be represented safely:

1. use a documented harness adapter only when the harness officially supports
   the mechanism;
2. report the capability and harness as degraded when no native equivalent
   exists; and
3. never hide the gap or introduce an implicit CLI wrapper.

## 6. Installation Flow

The coordinator will perform these operations in order:

1. Resolve one Manifest release version and source commit.
2. Load and validate the nine domain contracts.
3. Verify release provenance, checksums, and generated native views.
4. Detect requested harnesses and supported versions.
5. Acquire a machine-level mutation lock.
6. Snapshot only the settings files that adapters will modify.
7. Install all nine bundles at user scope through native managers.
8. Union and deduplicate external capability declarations.
9. Apply hooks, MCP servers, rules, agents, and settings through each adapter.
10. Verify effective capabilities rather than directory presence alone.
11. Atomically write the verified per-harness results to the installation
    receipt, including partial convergence when applicable.
12. Release the mutation lock and emit human-readable or structured results.

One release version must be used across all bundles and harnesses. Mixed bundle
generations are drift, even when every individual native manager reports that
its plugin is installed. Release resolution must use an immutable version or
commit plus published checksums; mutable branch heads are not an installation
identity.

## 7. Commands And State

The initial command surface is deliberately small:

```bash
uvx --from manifest-agent manifest install
uvx --from manifest-agent manifest migrate
uvx --from manifest-agent manifest reconcile
uvx --from manifest-agent manifest reconcile --apply
uvx --from manifest-agent manifest uninstall
```

- `install` converges a fresh or already-native installation and is idempotent.
- `migrate` performs the one-writer handoff from a bootstrap-managed machine.
- `reconcile` is read-only and reports drift.
- `reconcile --apply` repairs Manifest-owned drift.
- `uninstall` removes only Manifest-owned plugins and configuration entries.

The coordinator will write an XDG-compliant receipt containing the selected
release, source commit, bundle inventory, harness adapter versions, native
plugin identifiers, and verified capability states. The receipt contains no
credentials and is installation state, not a source configuration tree.

Each successfully verified harness is recorded even when another harness fails.
Failed or unverified operations are recorded with their result and error, but
never as installed capability claims. This makes partial convergence explicit
and gives `reconcile --apply` an authoritative repair basis.

Manifest-owned configuration entries must carry stable ownership markers.
Adapters merge those entries into native files and never replace entire user
configuration files.

## 8. Error And Concurrency Model

Result states are:

- `READY`: every requested capability is verified.
- `DEGRADED`: the installation works, but a default or natively unsupported
  capability is missing.
- `BLOCKED`: a required dependency, bundle, native operation, or verification
  step failed.
- `DRIFTED`: effective state no longer matches the selected release or contract.

The coordinator must:

- acquire a machine-level lock before any mutation;
- use atomic writes for owned state and receipts;
- propagate every adapter error into the final report;
- preserve successful harness installations when an unrelated harness fails;
- roll back the current harness when its adapter supports reliable rollback;
- name the exact repair command after partial convergence;
- preserve unrecognized plugins, MCP servers, hooks, rules, and settings; and
- use each harness's native credential and authentication storage.

A caught error may not become a warning followed by a successful verdict.

## 9. Migration From Bootstrap

The migration will proceed in stages while full six-harness parity remains the
release gate.

### Stage 1: Capability inventory

Inventory every bootstrap-owned capability and classify it as bundle-owned,
coordinator-owned, harness-native, user-owned, or retired. The inventory must
cover skills, agents, guidance, hooks, permissions, MCP, scripts, optional
tools, configuration, diagnostics, updates, and uninstall behavior.

### Stage 2: Bundle isolation

Make every domain bundle self-contained and remove runtime dependencies on
legacy home paths. Generate all harness-native views from the portable
contracts.

### Stage 3: Adapter completion

Implement and test all six adapters against isolated home directories. No
harness is accepted as a permanent exception to the parity contract.

### Stage 4: Shadow verification

Install native plugins into isolated homes, verify their capabilities, and
calculate the exact legacy paths that migration will retire. Do not allow both
legacy and native copies to load in a real agent session.

### Stage 5: Ownership handoff

`manifest migrate` will:

1. inventory and snapshot known legacy-owned state;
2. install and verify all requested native bundles;
3. disable legacy ownership;
4. remove only inventoried bootstrap outputs; and
5. write the native installation receipt.

If native verification fails, the previous deployment remains active. The
migration may not leave a domain with zero writers or two active writers.

### Stage 6: Bootstrap retirement

After all live harness probes pass, remove `bootstrap.sh`, `bootstrap/`, home
deployment functions, service toggles, symlink hubs, and obsolete ownership and
drift machinery. Keep historical documentation and a standalone recovery
artifact that does not execute retired bootstrap code.

## 10. Verification

The implementation is gated by:

- exact nine-bundle inventory and release consistency checks;
- immutable release provenance and checksum verification;
- schema validation and generated-view drift detection;
- adapter unit tests with fake native CLIs and isolated configuration;
- isolated-home integration tests for each harness;
- one live install smoke test per supported harness;
- offline execution after successful installation;
- idempotent install, migrate, reconcile, repair, and uninstall tests;
- preservation tests for unrelated user plugins and configuration;
- partial-failure, rollback, atomic-write, and concurrent-install tests;
- a capability matrix proving every bundle is discoverable and executable in
  every harness; and
- a repository gate forbidding bootstrap and legacy home-path runtime
  references.

Skipped or unverifiable checks must not produce a green parity verdict.

## 11. Completion Criteria

The migration is complete when:

- a fresh machine with `uv` and a supported harness can install Manifest using
  one `uvx` command;
- an existing bootstrap-managed machine can migrate without duplicate skills
  or lost user configuration;
- all nine bundles provide equivalent applicable capabilities across Claude,
  Codex, Gemini, Cursor, Antigravity, and Devin;
- installed bundles work offline without bootstrap, `uvx`, or a shared runtime;
- native package managers own plugin download, update, caching, and removal;
- `manifest reconcile` detects effective capability and release drift;
- no runtime path depends on `~/.claude` as shared infrastructure; and
- the repository no longer needs bootstrap for installation, updates, repair,
  rollback, or removal.

## 12. Out Of Scope

- Installing or updating Claude Code, Codex, Gemini, Cursor, Antigravity, or
  Devin themselves.
- A universal plugin format that replaces each harness's native packaging.
- Automatic installation of optional MCP servers or authenticated services.
- Deploying configuration specifically to emdash.
- Maintaining separate hand-edited copies of domain capabilities per harness.
- Introducing a permanent shared Manifest runtime or a `manifest-core` plugin.
