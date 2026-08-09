# Codex Bootstrap Plugin Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bootstrap converge Codex to every plugin in the local Manifest marketplace and retire the duplicate flat
skill catalog only after native verification succeeds.

**Architecture:** Add a validated marketplace catalog beside the existing eight portable domain contracts, teach the
Codex adapter to reconcile that complete catalog, and expose a receipt-aware `manifest bootstrap-sync` coordinator
operation. Keep the legacy skill-link cutover in a focused, ownership-proven module and invoke the coordinator from
bootstrap after shared files are deployed.

**Tech Stack:** Python 3.11, Click, JSON, `tomllib`, existing `manifest_agent` adapters and receipts, Bash
3.2-compatible bootstrap code, pytest, Bats.

## Global Constraints

- The local `.claude-plugin/marketplace.json` is the canonical bootstrap plugin inventory.
- Portable domain contracts remain the source of component and capability verification; marketplace-only addons still
  require exact name/version verification.
- Never remove `~/.codex/skills` before all required Codex plugins verify as installed and enabled.
- Never delete unowned plugins, Codex auth/history/session state, or unrelated `config.toml` settings.
- Every native command result must be parsed and surfaced through a redacted `ServiceReport`.
- A failed enabled-Codex convergence makes bootstrap return non-zero.
- Repeated bootstrap runs must be idempotent.

---

## File Structure

- Create `src/manifest_agent/catalog.py`: validate marketplace entries and expose the complete install inventory.
- Create `src/manifest_agent/bootstrap_sync.py`: choose install/reconcile behavior and coordinate final cutovers.
- Create `src/manifest_agent/codex_skill_cutover.py`: ownership-check, retire, and restore only the Manifest-managed
  Codex skills link.
- Modify `src/manifest_agent/models.py`: carry `CatalogPlugin` records in `DesiredState`.
- Modify `src/manifest_agent/service.py`: construct catalog-aware desired state and expose `bootstrap_sync()`.
- Modify `src/manifest_agent/cli.py`: add the `bootstrap-sync` command.
- Modify `src/manifest_agent/adapters/codex.py`: reconcile the complete catalog instead of only `DOMAIN_BUNDLES`.
- Modify `bootstrap/lib/deploy.sh`: replace the shell coverage heuristic with the coordinator call.
- Test in `tests/python/manifest_agent/test_catalog.py`, `test_adapter_codex.py`, `test_bootstrap_sync.py`,
  `test_codex_skill_cutover.py`, `test_cli.py`, and `tests/bats/deploy_skills.bats`.

### Task 1: Add a Validated Marketplace Catalog

**Files:**

- Create: `src/manifest_agent/catalog.py`
- Modify: `src/manifest_agent/models.py`
- Modify: `src/manifest_agent/service.py`
- Test: `tests/python/manifest_agent/test_catalog.py`
- Test: `tests/python/manifest_agent/conftest.py`

**Interfaces:**

- Produces: `CatalogPlugin(name: str, version: str, source: str)`.
- Produces: `load_catalog(path: Path) -> tuple[CatalogPlugin, ...]`.
- Produces: `DesiredState.catalog_plugins: tuple[CatalogPlugin, ...]`.
- Preserves: `DesiredState.contracts` for portable component verification.

- [ ] **Step 1: Write catalog validation tests**

```python
def test_catalog_preserves_marketplace_order(repo_root):
    catalog = load_catalog(repo_root / ".claude-plugin/marketplace.json")
    assert [plugin.name for plugin in catalog][-3:] == [
        "adversarial-design-loop",
        "manifest-delegate",
        "manifest-docker",
    ]


def test_catalog_rejects_duplicate_names(tmp_path):
    marketplace = tmp_path / "marketplace.json"
    marketplace.write_text(
        '{"plugins":['
        '{"name":"one","version":"1.0.0","source":"./plugins/one"},'
        '{"name":"one","version":"1.0.1","source":"./plugins/two"}'
        ']}'
    )
    with pytest.raises(CatalogError, match="duplicate plugin name"):
        load_catalog(marketplace)
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run: `uv run pytest tests/python/manifest_agent/test_catalog.py -q`

Expected: FAIL because `manifest_agent.catalog` and `CatalogPlugin` do not exist.

- [ ] **Step 3: Implement the immutable catalog model and loader**

```python
@dataclass(frozen=True)
class CatalogPlugin:
    name: str
    version: str
    source: str


def load_catalog(path: Path) -> tuple[CatalogPlugin, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("plugins")
    if not isinstance(rows, list) or not rows:
        raise CatalogError("marketplace plugins are required")
    plugins = tuple(_decode_plugin(path.parent.parent, row) for row in rows)
    names = [plugin.name for plugin in plugins]
    if len(names) != len(set(names)):
        raise CatalogError("duplicate plugin name in marketplace")
    return plugins
```

Validate non-empty names/versions, relative sources contained by the repository, matching plugin directories, and exact
source existence. Do not infer versions from directory contents.

- [ ] **Step 4: Add `catalog_plugins` to desired-state construction**

Update `ManifestService._desired_state()` so it loads:

```python
catalog_plugins=load_catalog(resolved.release_root / ".claude-plugin/marketplace.json")
```

Update every `DesiredState` fixture constructor to pass a tuple of catalog entries. Test helpers should derive entries
from `DOMAIN_BUNDLES` plus fixture addons instead of hardcoding an empty tuple.

- [ ] **Step 5: Run catalog and desired-state tests**

Run: `uv run pytest tests/python/manifest_agent/test_catalog.py tests/python/manifest_agent/test_service_install.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manifest_agent/catalog.py src/manifest_agent/models.py src/manifest_agent/service.py tests/python/manifest_agent/test_catalog.py tests/python/manifest_agent/conftest.py tests/python/manifest_agent/test_service_install.py
git commit -m "feat(catalog): load canonical marketplace plugins"
```

### Task 2: Reconcile the Complete Catalog in Codex

**Files:**

- Modify: `src/manifest_agent/adapters/codex.py`
- Modify: `src/manifest_agent/adapters/codex_native.py`
- Test: `tests/python/manifest_agent/test_adapter_codex.py`
- Test: `tests/python/manifest_agent/test_adapter_codex_sources.py`

**Interfaces:**

- Consumes: `DesiredState.catalog_plugins` from Task 1.
- Produces: `CodexAdapter.install(desired) -> HarnessResult` containing every catalog plugin ID.
- Produces: exact states for missing, disabled, wrong-version, and ready plugins.

- [ ] **Step 1: Add failing full-catalog tests**

Add cases proving:

```python
assert [row[3] for row in runner.log if row[:3] == ["codex", "plugin", "add"]] == [
    f"{plugin.name}@manifest" for plugin in desired.catalog_plugins
]
```

Also add tests where:

- `manifest-delegate` and `manifest-docker` are absent.
- A catalog plugin is installed with `enabled: false`.
- A catalog plugin reports the wrong version.
- Domain components still use `desired.contracts` for deep evidence checks.

- [ ] **Step 2: Run the adapter tests and confirm the addon cases fail**

Run:

```bash
uv run pytest tests/python/manifest_agent/test_adapter_codex.py \
  tests/python/manifest_agent/test_adapter_codex_sources.py -q
```

Expected: FAIL because the adapter loops over `desired.contracts` only.

- [ ] **Step 3: Split catalog verification from contract component verification**

Implement:

```python
def _verify_catalog_rows(
    desired: DesiredState, rows: Sequence[Mapping[str, Any]]
) -> HarnessResult:
    expected = {plugin.name: plugin for plugin in desired.catalog_plugins}
    # Return DRIFTED for missing, disabled, or wrong-version entries.


def _catalog_plugin_ids(desired: DesiredState) -> tuple[str, ...]:
    return tuple(f"{plugin.name}@manifest" for plugin in desired.catalog_plugins)
```

Keep `_component_evidence()` and `verify_declared_components()` scoped to portable contracts.

- [ ] **Step 4: Make installation repair missing, disabled, and stale plugins**

For missing plugins, run `codex plugin add <name>@manifest --json`. For a Manifest plugin that is installed but
disabled or stale, run `codex plugin remove <name>@manifest --json`, then add it again. Never remove an installed
plugin from another marketplace.

Return the successful installed IDs as:

```python
tuple(f"{plugin.name}@manifest" for plugin in desired.catalog_plugins)
```

- [ ] **Step 5: Verify exact JSON mutation handling**

Extend `codex_native.py` validators so remove/add responses must identify the requested plugin and resulting
installed/enabled state. A zero exit with malformed JSON remains `BLOCKED`.

- [ ] **Step 6: Run adapter tests**

Run:

```bash
uv run pytest tests/python/manifest_agent/test_adapter_codex.py \
  tests/python/manifest_agent/test_adapter_codex_sources.py \
  tests/python/manifest_agent/test_native_adapter_integration.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/adapters/codex.py src/manifest_agent/adapters/codex_native.py tests/python/manifest_agent/test_adapter_codex.py tests/python/manifest_agent/test_adapter_codex_sources.py tests/python/manifest_agent/test_native_adapter_integration.py
git commit -m "feat(codex): reconcile the complete plugin catalog"
```

### Task 3: Add Transactional Codex Skill Cutover

**Files:**

- Create: `src/manifest_agent/codex_skill_cutover.py`
- Modify: `src/manifest_agent/models.py`
- Modify: `src/manifest_agent/state.py`
- Test: `tests/python/manifest_agent/test_codex_skill_cutover.py`

**Interfaces:**

- Produces: `inspect_codex_skill_source(home: Path, expected_target: Path) -> SkillSourceState`.
- Produces: `cutover_codex_skills(home: Path, expected_target: Path) -> OwnedEntry`.
- Produces: `restore_codex_skills(entry: OwnedEntry) -> None`.

- [ ] **Step 1: Write ownership and rollback tests**

Cover the exact states:

```python
def test_cutover_replaces_only_manifest_owned_link(tmp_path):
    home = tmp_path / "home"
    source = home / ".manifest" / "skills"
    source.mkdir(parents=True)
    (source / ".system").mkdir()
    codex = home / ".codex"
    codex.mkdir()
    (codex / "skills").symlink_to(source)

    owned = cutover_codex_skills(home, source)

    assert not (codex / "skills").is_symlink()
    assert (codex / "skills" / ".system").resolve() == source / ".system"
    assert owned.identifier == "codex-shared-skills"
```

Add separate tests with complete setup and assertions for a user-managed link, a missing `.system` source, restoration
of the prior Manifest link, and an idempotent second cutover.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/python/manifest_agent/test_codex_skill_cutover.py -q`

Expected: FAIL because the cutover module does not exist.

- [ ] **Step 3: Implement strict skill-source classification**

```python
@dataclass(frozen=True)
class SkillSourceState:
    kind: Literal["legacy-link", "system-only", "user-managed", "missing"]
    path: Path
    target: str | None = None
```

Treat a symlink as Manifest-owned only when its resolved target equals the configured `MANIFEST_SKILLS_DIR`. Never
follow or replace another target.

- [ ] **Step 4: Implement atomic cutover and receipt ownership**

Rename the owned link to a private sibling, create `~/.codex/skills`, link `.system` when the source has `.system`,
fsync the parent, then remove the private sibling. Return an `OwnedEntry` containing the prior symlink target and the
created path identity.

On any exception, restore the renamed link before propagating a typed error.

- [ ] **Step 5: Extend receipt validation for the new owned-entry kind**

Allow only the exact `codex-skill-source` kind, require `target_path` to resolve under `.codex/skills`, and reject
missing prior targets or credential-like content.

- [ ] **Step 6: Run cutover and receipt tests**

Run:
`uv run pytest tests/python/manifest_agent/test_codex_skill_cutover.py tests/python/manifest_agent/test_state.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/codex_skill_cutover.py src/manifest_agent/models.py src/manifest_agent/state.py tests/python/manifest_agent/test_codex_skill_cutover.py tests/python/manifest_agent/test_state.py
git commit -m "feat(codex): make skill cutover transactional"
```

### Task 4: Add `manifest bootstrap-sync`

**Files:**

- Create: `src/manifest_agent/bootstrap_sync.py`
- Modify: `src/manifest_agent/service.py`
- Modify: `src/manifest_agent/cli.py`
- Test: `tests/python/manifest_agent/test_bootstrap_sync.py`
- Test: `tests/python/manifest_agent/test_cli.py`

**Interfaces:**

- Produces: `BootstrapSyncService.run(desired: DesiredState) -> ServiceReport`.
- Produces: `ManifestService.bootstrap_sync() -> ServiceReport`.
- Produces: `reconcile_owned_harnesses(service, receipt, desired, selected, apply) -> ServiceReport`.
- Produces CLI: `manifest bootstrap-sync --source PATH --harness codex --non-interactive --json`.

- [ ] **Step 1: Write state-selection tests**

Test these branches:

```python
def test_bootstrap_sync_cuts_over_only_after_ready(service_factory, legacy_link):
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"codex": codex}, harnesses=("codex",))

    report = service.bootstrap_sync()

    assert report.state is ResultState.READY
    assert codex.calls == ["detect", "install", "inspect"]
    assert not legacy_link.is_symlink()
```

Add independent tests for initial install without a receipt, existing-receipt reconciliation, partial identity-change
blocking, blocked-install link preservation, and a no-op second run.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/python/manifest_agent/test_bootstrap_sync.py tests/python/manifest_agent/test_cli.py -q`

Expected: FAIL because the operation and CLI command do not exist.

- [ ] **Step 3: Implement receipt-aware synchronization**

Under the existing installation lock:

```python
receipt = read_receipt(self.receipt_path)
if receipt is None:
    result = adapter.install(desired)
else:
    result = reconcile_owned_harnesses(
        service=self,
        receipt=receipt,
        desired=desired,
        selected=selected,
        apply=True,
    )
verified = adapter.inspect(desired)
if verified.state is ResultState.READY:
    owned_entry = cutover_codex_skills(home, manifest_skills_dir)
```

When a release identity changes, synchronize every receipt-owned harness in the same operation. If any owned harness is
unavailable, return `BLOCKED` before changing receipt identity or cutting over Codex skills.

- [ ] **Step 4: Persist the cutover only after final inspection**

Combine the cutover `OwnedEntry` with the adapter result, rebuild the receipt, and atomically write it. If receipt
writing fails after cutover, call `restore_codex_skills()` and return `BLOCKED`.

- [ ] **Step 5: Add CLI wiring and stable JSON tests**

```python
@cli.command("bootstrap-sync")
@_lifecycle_options
@click.pass_context
def bootstrap_sync(context: click.Context, **options: Any) -> None:
    _emit(context, _service(**options).bootstrap_sync(), options["as_json"])
```

- [ ] **Step 6: Run service and CLI tests**

Run:

```bash
uv run pytest tests/python/manifest_agent/test_bootstrap_sync.py \
  tests/python/manifest_agent/test_cli.py \
  tests/python/manifest_agent/test_concurrent_operations.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/bootstrap_sync.py src/manifest_agent/service.py src/manifest_agent/cli.py tests/python/manifest_agent/test_bootstrap_sync.py tests/python/manifest_agent/test_cli.py tests/python/manifest_agent/test_concurrent_operations.py
git commit -m "feat: add receipt-aware bootstrap sync"
```

### Task 5: Replace Bootstrap's Shell Heuristic

**Files:**

- Modify: `bootstrap/lib/deploy.sh`
- Modify: `bootstrap/lib/common.sh`
- Test: `tests/bats/deploy_skills.bats`
- Test: `tests/bats/bootstrap_services.bats`

**Interfaces:**

- Consumes: `manifest bootstrap-sync` from Task 4.
- Removes: `codex_manifest_plugins_cover_catalog()` and shell-owned cutover decisions.
- Produces: `sync_native_plugins() -> 0|nonzero` with human-readable and JSON-backed diagnostics.

- [ ] **Step 1: Add failing isolated-home Bats cases**

Stub `manifest` and assert bootstrap invokes:

```text
manifest bootstrap-sync --source <repo> --harness codex --non-interactive --json
```

Add cases for READY, BLOCKED, Codex disabled, and Codex CLI absent. A BLOCKED enabled target must make `deploy_configs`
fail.

- [ ] **Step 2: Run the Bats tests and confirm they fail**

Run: `bats tests/bats/deploy_skills.bats tests/bats/bootstrap_services.bats`

Expected: FAIL because bootstrap still uses `codex_manifest_plugins_cover_catalog()`.

- [ ] **Step 3: Implement the coordinator bridge**

Add a small function that locates the repository's `manifest-agent` entry point without installing dependencies. Prefer
the active repository environment (`uv run --project "$SCRIPT_DIR" manifest bootstrap-sync`) and fail with an explicit
message when `uv` or the coordinator is unavailable.

Parse the JSON state with Python already required by the coordinator; do not scrape prose output.

- [ ] **Step 4: Remove the old shell cutover functions**

Delete `codex_manifest_plugins_cover_catalog()` and reduce `configure_codex_skill_source()` to pre-coordinator
legacy-link setup only. The coordinator owns final retirement.

- [ ] **Step 5: Run bootstrap tests**

Run: `bats tests/bats/deploy_skills.bats tests/bats/bootstrap_services.bats tests/bats/bootstrap_common.bats`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bootstrap/lib/deploy.sh bootstrap/lib/common.sh tests/bats/deploy_skills.bats tests/bats/bootstrap_services.bats
git commit -m "feat(bootstrap): reconcile Codex plugins through coordinator"
```

### Task 6: Add Native Regression Coverage and Documentation

**Files:**

- Create: `tests/python/manifest_agent/test_codex_bootstrap_native.py`
- Modify: `docs/CONFIGURATION.md`
- Modify: `docs/TROUBLESHOOTING.md`
- Modify: `docs/PLUGIN_RELEASE.md`

**Interfaces:**

- Verifies the user-observed nine-installed/two-missing state.
- Documents automatic plugin convergence and recovery commands.

- [ ] **Step 1: Add an opt-in native Codex smoke test**

Mark it `@pytest.mark.native`. Use an isolated `HOME`, register the repository marketplace, preinstall only the first
nine entries, create the legacy skills symlink, and run `manifest bootstrap-sync` twice.

Assert the first run installs `manifest-delegate` and `manifest-docker`, converts the skill source, and returns READY.
Assert the second run reports no mutations.

- [ ] **Step 2: Add troubleshooting documentation**

Document:

- How to inspect `codex plugin list --marketplace manifest --json`.
- Why the flat skill link remains after a failed convergence.
- How to rerun `manifest bootstrap-sync --source <checkout> --harness codex`.
- That bootstrap now fails instead of claiming success when required plugins are missing.

- [ ] **Step 3: Run focused verification**

Run:

```bash
uv run pytest tests/python/manifest_agent/test_catalog.py \
  tests/python/manifest_agent/test_adapter_codex.py \
  tests/python/manifest_agent/test_codex_skill_cutover.py \
  tests/python/manifest_agent/test_bootstrap_sync.py \
  tests/python/manifest_agent/test_cli.py -q
bats tests/bats/deploy_skills.bats tests/bats/bootstrap_services.bats
pre-commit run --files src/manifest_agent/catalog.py src/manifest_agent/bootstrap_sync.py \
  src/manifest_agent/codex_skill_cutover.py src/manifest_agent/adapters/codex.py \
  bootstrap/lib/deploy.sh
```

Expected: all focused tests pass. Run the native test only on a disposable authenticated Codex environment.

- [ ] **Step 4: Commit**

```bash
git add tests/python/manifest_agent/test_codex_bootstrap_native.py docs/CONFIGURATION.md docs/TROUBLESHOOTING.md docs/PLUGIN_RELEASE.md
git commit -m "test(codex): cover bootstrap plugin reconciliation"
```
