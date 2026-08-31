# Bootstrap-Free Cross-Harness Plugin Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `bootstrap.sh` with an ephemeral `uvx --from manifest-agent manifest ...` coordinator that installs, migrates, reconciles, and removes the nine self-contained Manifest domain bundles across Claude Code, Codex, Gemini CLI, Cursor, Antigravity, and Devin.

**Architecture:** Each domain bundle owns one portable `manifest-capabilities.yml`; generated native manifests are checked release artifacts. The `manifest-agent` Python package contains only release resolution, adapter orchestration, capability merging, receipts, and migration logic. Runtime behavior moves into bundle-local assets or cross-skill interfaces so installed bundles work offline without bootstrap, `uvx`, a shared home tree, or a permanent Manifest executable.

**Tech Stack:** Python 3.11+, Click, PyYAML, jsonschema, stdlib dataclasses/pathlib/subprocess/hashlib/tarfile/fcntl, pytest, Bats, JSON Schema, existing Claude/Codex plugin marketplace format, Gemini extension manifests, native harness CLIs, GitHub Actions.

## Global Constraints

- The capability source is exactly nine domain bundles: `manifest-code-quality`, `manifest-docs`, `manifest-forge`, `manifest-graphify`, `manifest-ops`, `manifest-security`, `manifest-spec-planning`, `manifest-workspace`, and `stitch-design`.
- `adversarial-design-loop` remains an independent optional plugin and is excluded from the nine-bundle parity verdict.
- Full parity means equivalent applicable capabilities across Claude, Codex, Gemini, Cursor, Antigravity, and Devin; identical file layouts are not required.
- Install all nine bundles at user scope into every detected supported harness by default.
- Do not install or update the six harness CLIs.
- After installation, no skill may invoke `bootstrap.sh`, `uvx`, `manifest-agent`, `~/.claude/scripts`, `~/.claude/config`, or another plugin through path arithmetic.
- Installed bundle behavior must work offline; network access is permitted only for capabilities whose purpose explicitly requires it.
- Installed bundle executables use Python stdlib only or package a locked, checksummed dependency inside the owning bundle; they never assume the ephemeral coordinator's virtual environment remains available.
- There is no `manifest-core` plugin and no permanent shared Manifest runtime.
- External capabilities are explicit and tiered as `required`, `default`, or `optional`; optional MCP servers are never inferred from prose.
- One immutable release version, source commit, and checksum set applies across all bundles and harnesses in one operation.
- Preserve unrelated plugins, hooks, MCP servers, rules, credentials, and user settings.
- Every adapter error reaches the final result; skipped or unverifiable checks never become green parity.
- Mutations are locked and atomic; receipts contain no secrets.
- The PyPI distribution name is `manifest-agent` and the console command is `manifest`; `manifest-agent` returned 404 from the PyPI JSON API on 2026-08-01, while `manifest` is already occupied.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Publishable `manifest-agent` project plus existing repo tooling configuration |
| `uv.lock` | Committed coordinator resolution generated from root `pyproject.toml` |
| `src/manifest_agent/models.py` | Immutable contracts, desired state, adapter results, receipts, and verdict enums |
| `src/manifest_agent/contracts.py` | Schema validation and nine-bundle contract loading |
| `src/manifest_agent/release.py` | Immutable release resolution, archive acquisition, and checksum verification |
| `src/manifest_agent/paths.py` | XDG config/data/state/cache paths; no `~/.claude` fallback |
| `src/manifest_agent/state.py` | Machine lock, atomic JSON receipt writes, and owned-entry metadata |
| `src/manifest_agent/process.py` | Injected subprocess runner with captured stdout/stderr and no shell interpolation |
| `src/manifest_agent/capabilities.py` | Required/default/optional union, conflict detection, and selection |
| `src/manifest_agent/migration.py` | Legacy inventory, shadow verification, one-writer handoff, rollback, and recovery metadata |
| `src/manifest_agent/adapters/base.py` | Harness adapter protocol and common verification helpers |
| `src/manifest_agent/adapters/*.py` | One adapter each for Claude, Codex, Gemini, Cursor, Antigravity, and Devin |
| `src/manifest_agent/service.py` | Install, migrate, reconcile, repair, and uninstall orchestration |
| `src/manifest_agent/cli.py` | Click command surface and JSON/human rendering |
| `src/manifest_agent/data/mcp_catalog.yml` | Coordinator-owned transport definitions for declared MCP identifiers |
| `src/manifest_agent/data/executable_catalog.yml` | Explicit user-scope acquisition recipes for coordinator-managed external tools; system tools are check-only |
| `src/manifest_agent/data/legacy_inventory.yml` | Exact bootstrap-owned paths, ownership proofs, retirement actions, and destination classifications |
| `schemas/manifest-capabilities.schema.json` | Portable bundle contract schema, including components, tiered capabilities, compatibility, and provenance |
| `plugins/*/manifest-capabilities.yml` | Canonical per-domain component and capability declarations |
| `plugins/*/runtime/` | Same-domain shared scripts/config/references packaged inside that bundle only |
| `plugins/*/.claude-plugin/plugin.json` | Generated Claude/Codex/Cursor view |
| `plugins/*/gemini-extension.json` | Generated Gemini extension view |
| `plugins/*/plugin.json` | Generated generic import view used by Antigravity and Devin adapters |
| `tools/generate_plugin_views.py` | Deterministic native-view and marketplace generator |
| `tools/check_plugin_runtime_paths.py` | Final zero-tolerance gate for bootstrap and shared-home runtime references |
| `tests/python/manifest_agent/` | Coordinator unit and integration tests with fake harness CLIs |
| `tests/fixtures/plugin_contracts/` | Minimal valid/invalid contracts and expected generated manifests |
| `tests/fixtures/harness_bins/` | Executable harness stubs that record argv and return controlled JSON/text |
| `tests/bats/plugin_offline_runtime.bats` | Representative bundle-local execution with no deployed home tree |
| `tests/bats/plugin_migration.bats` | One-writer migration, rollback, preservation, and idempotency |
| `docs/PLUGIN_CAPABILITY_INVENTORY.md` | Generated human-readable legacy-to-native capability disposition |
| `docs/PLUGIN_CAPABILITY_MATRIX.md` | Generated bundle-by-harness parity evidence and explicit degraded cells |
| `.github/workflows/plugin-parity-live.yml` | Release-blocking live matrix for all six harnesses |

## Stable Interfaces

These names are fixed for every task below:

```python
class ResultState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    DRIFTED = "DRIFTED"


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class HarnessResult:
    harness: str
    state: ResultState
    installed_plugin_ids: tuple[str, ...]
    capabilities: dict[str, str]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class HarnessAdapter(Protocol):
    name: str

    def detect(self) -> Detection: ...
    def inspect(self, desired: DesiredState) -> HarnessResult: ...
    def install(self, desired: DesiredState) -> HarnessResult: ...
    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult: ...
```

The service layer consumes only this protocol. Adapter modules must not import one another.

Receipt and desired-state fields are also stable:

```python
@dataclass(frozen=True)
class DesiredState:
    release_version: str
    source_commit: str
    source: str
    release_root: Path
    repository_url: str
    source_dirty: bool
    archive_sha256: str
    contracts: tuple[BundleContract, ...]
    selected_optional: frozenset[str]
    requested_harnesses: tuple[str, ...]

    def bundle_path(self, name: str) -> Path:
        return self.release_root / "plugins" / name


@dataclass(frozen=True)
class OwnedEntry:
    kind: str
    identifier: str
    ownership_marker: str
    target_path: str | None = None
    previous_checksum: str | None = None


@dataclass(frozen=True)
class HarnessReceipt:
    harness: str
    adapter_version: str
    native_version: str
    plugin_ids: tuple[str, ...]
    owned_entries: tuple[OwnedEntry, ...]
    capabilities: dict[str, str]
    verified: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstallationReceipt:
    schema_version: int
    coordinator_version: str
    release_version: str
    source_commit: str
    source_dirty: bool
    archive_sha256: str
    bundle_checksums: dict[str, str]
    selected_optional: tuple[str, ...]
    harnesses: dict[str, HarnessReceipt]
    migration_backup: str | None = None
```

`OwnedEntry` records a native identifier, ownership marker, target path when applicable, and pre-install value checksum. It never stores a token, header, environment value, or native credential payload.

---

### Task 1: Create the Publishable Coordinator Package and Core Models

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `uv.lock` (generated by `uv lock`)
- Create: `src/manifest_agent/__init__.py`
- Create: `src/manifest_agent/__main__.py`
- Create: `src/manifest_agent/models.py`
- Create: `src/manifest_agent/paths.py`
- Create: `src/manifest_agent/cli.py`
- Create: `tests/python/manifest_agent/test_models.py`
- Create: `tests/python/manifest_agent/test_paths.py`
- Create: `tests/python/manifest_agent/test_cli.py`

**Interfaces:**
- Consumes: none
- Produces: `ResultState`, `CapabilityTier`, `BundleContract`, `DesiredState`, `OwnedEntry`, `HarnessReceipt`, `HarnessResult`, `InstallationReceipt`, `xdg_paths()`, and the `manifest` console entry point

- [ ] **Step 1: Write failing model and XDG-path tests**

```python
from manifest_agent.models import CapabilityTier, ResultState
from manifest_agent.paths import xdg_paths


def test_result_states_are_stable_strings():
    assert [state.value for state in ResultState] == [
        "READY",
        "DEGRADED",
        "BLOCKED",
        "DRIFTED",
    ]


def test_xdg_paths_never_fall_back_to_claude_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    paths = xdg_paths()
    assert paths.state == tmp_path / ".local/state/manifest"
    assert ".claude" not in str(paths)


def test_cli_lists_only_control_plane_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert all(
        name in result.output
        for name in ("install", "migrate", "reconcile", "uninstall")
    )
    assert "parallel-agent" not in result.output
```

- [ ] **Step 2: Run the focused tests and verify import failure**

Run: `pytest tests/python/manifest_agent/test_models.py tests/python/manifest_agent/test_paths.py tests/python/manifest_agent/test_cli.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'manifest_agent'`.

- [ ] **Step 3: Add the root project metadata and committed lock exception**

Add to `pyproject.toml` without removing the existing Ruff, pytest, coverage, or pyright sections:

```toml
[project]
name = "manifest-agent"
version = "0.1.0"
description = "Bootstrap-free installer for Manifest agent plugin bundles"
requires-python = ">=3.11"
dependencies = [
  "click>=8.1,<9",
  "jsonschema>=4.23,<5",
  "pyyaml>=6.0.1,<7",
]

[project.scripts]
manifest = "manifest_agent.cli:main"

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/manifest_agent"]
```

Change `.gitignore` from an unconditional root `uv.lock` ignore to:

```gitignore
!uv.lock
!configs/claude/uv.lock
```

Run: `uv lock`

Expected: root `uv.lock` records `manifest-agent` and the three bounded runtime dependencies. Before locking, verify the exact distributions exist on PyPI, retain compatible licenses, and have no active critical advisory.

- [ ] **Step 4: Implement the enums, frozen dataclasses, XDG resolver, and CLI skeleton**

```python
class CapabilityTier(StrEnum):
    REQUIRED = "required"
    DEFAULT = "default"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class XdgPaths:
    config: Path
    data: Path
    state: Path
    cache: Path


def xdg_paths() -> XdgPaths:
    home = Path.home()
    return XdgPaths(
        config=Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "manifest",
        data=Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "manifest",
        state=Path(os.environ.get("XDG_STATE_HOME", home / ".local/state"))
        / "manifest",
        cache=Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "manifest",
    )
```

The four Click commands initially raise `ClickException("not implemented")`; do not expose the legacy runtime commands.

- [ ] **Step 5: Run package and CLI tests**

Run: `uv run pytest tests/python/manifest_agent/test_models.py tests/python/manifest_agent/test_paths.py tests/python/manifest_agent/test_cli.py -v`

Expected: PASS.

- [ ] **Step 6: Verify the wheel and console entry point**

Run: `uv build && uv run manifest --help`

Expected: wheel builds; help lists `install`, `migrate`, `reconcile`, and `uninstall` only.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src/manifest_agent tests/python/manifest_agent
git commit -m "feat(installer): scaffold manifest-agent coordinator"
```

---

### Task 2: Define and Validate the Portable Bundle Contract

**Files:**
- Modify: `pyproject.toml`
- Create: `schemas/manifest-capabilities.schema.json`
- Create: `src/manifest_agent/data/__init__.py`
- Create: `src/manifest_agent/contracts.py`
- Create: `tests/fixtures/plugin_contracts/minimal-valid.yml`
- Create: `tests/fixtures/plugin_contracts/unknown-tier.yml`
- Create: `tests/fixtures/plugin_contracts/missing-bundle.yml`
- Create: `tests/python/manifest_agent/test_contracts.py`

**Interfaces:**
- Consumes: `BundleContract`, `CapabilityTier` from Task 1
- Produces: `load_contract(path: Path) -> BundleContract` and `load_domain_contracts(root: Path) -> tuple[BundleContract, ...]`

- [ ] **Step 1: Write failing schema and catalog tests**

```python
def test_loads_minimal_contract(fixtures_dir):
    contract = load_contract(fixtures_dir / "minimal-valid.yml")
    assert contract.name == "manifest-docs"
    assert contract.components.skills_root == "skills"


def test_unknown_capability_tier_fails_closed(fixtures_dir):
    with pytest.raises(ContractError, match="unknown capability tier"):
        load_contract(fixtures_dir / "unknown-tier.yml")


def test_domain_loader_requires_exact_nine(tmp_path):
    with pytest.raises(ContractError, match="expected 9 domain contracts"):
        load_domain_contracts(tmp_path)
```

- [ ] **Step 2: Run tests and verify the loader is absent**

Run: `uv run pytest tests/python/manifest_agent/test_contracts.py -v`

Expected: FAIL because `manifest_agent.contracts` does not exist.

- [ ] **Step 3: Add the JSON Schema**

The schema must require these keys and reject additional top-level properties:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "bundle", "components", "capabilities", "compatibility", "provenance"],
  "properties": {
    "schema_version": {"const": 1},
    "bundle": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "version", "description", "category"],
      "properties": {
        "name": {"type": "string", "pattern": "^(manifest-[a-z0-9-]+|stitch-design)$"},
        "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
        "description": {"type": "string", "minLength": 20},
        "category": {"type": "string", "minLength": 1}
      }
    },
    "components": {"type": "object"},
    "capabilities": {"type": "object"},
    "compatibility": {"type": "object"},
    "provenance": {"type": "object"}
  }
}
```

Add the schema to the wheel without creating a second maintained copy:

```toml
[tool.hatch.build.targets.wheel.force-include]
"schemas/manifest-capabilities.schema.json" = "manifest_agent/data/manifest-capabilities.schema.json"
```

Define the nested objects rather than leaving them open-ended:

- `components.skills` requires `root` and `include`. `agents`, `hooks`, `runtime`, and `guidance` are arrays of objects requiring stable `id` and normalized relative `path` with no `..` segment; an optional six-harness `compatibility` override uses the same mode/reason object as the bundle default.
- `capabilities.mcp` and `capabilities.executables` each require `required`, `default`, and `optional` arrays of unique lowercase identifiers.
- `compatibility` requires exactly `claude`, `codex`, `gemini`, `cursor`, `antigravity`, and `devin`. Each value is an object with `mode` set to `native`, `generated`, `imported`, `degraded`, or `unsupported`; `reason` is required and non-empty for the last two modes and forbidden otherwise.
- `provenance` requires the canonical repository URL, SPDX license identifier, license-file path, and `generated_by: tools/generate_plugin_views.py`.

- [ ] **Step 4: Implement strict loading and semantic checks**

Load the wheel-packaged schema with `importlib.resources.files("manifest_agent.data")`. Use `jsonschema.Draft202012Validator.iter_errors()` so `load_contract()` reports all structural violations before semantic checks. `load_domain_contracts()` must use the fixed domain-name tuple from the approved design, reject duplicates, reject `adversarial-design-loop`, verify every declared component path and `components.skills.root` directory remains inside its bundle, and report every validation error before raising `ContractError`.

```python
DOMAIN_BUNDLES = (
    "manifest-code-quality",
    "manifest-docs",
    "manifest-forge",
    "manifest-graphify",
    "manifest-ops",
    "manifest-security",
    "manifest-spec-planning",
    "manifest-workspace",
    "stitch-design",
)
```

- [ ] **Step 5: Run contract tests**

Run: `uv run pytest tests/python/manifest_agent/test_contracts.py -v && uv build`

Expected: tests pass and the wheel contains `manifest_agent/data/manifest-capabilities.schema.json`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml schemas/manifest-capabilities.schema.json src/manifest_agent/data/__init__.py src/manifest_agent/contracts.py tests/fixtures/plugin_contracts tests/python/manifest_agent/test_contracts.py
git commit -m "feat(plugins): define portable capability contract"
```

---

### Task 3: Add the Nine Canonical Contracts and Generate Native Views

**Files:**
- Create: `plugins/{manifest-code-quality,manifest-docs,manifest-forge,manifest-graphify,manifest-ops,manifest-security,manifest-spec-planning,manifest-workspace,stitch-design}/manifest-capabilities.yml`
- Create: `tools/generate_plugin_views.py`
- Create: `tools/skill_ref.py`
- Modify: `.claude-plugin/marketplace.json` (generated)
- Modify: `plugins/{manifest-code-quality,manifest-docs,manifest-forge,manifest-graphify,manifest-ops,manifest-security,manifest-spec-planning,manifest-workspace,stitch-design}/.claude-plugin/plugin.json` (generated)
- Create: `plugins/{manifest-code-quality,manifest-docs,manifest-forge,manifest-graphify,manifest-ops,manifest-security,manifest-spec-planning,manifest-workspace,stitch-design}/gemini-extension.json` (generated)
- Create: `plugins/{manifest-code-quality,manifest-docs,manifest-forge,manifest-graphify,manifest-ops,manifest-security,manifest-spec-planning,manifest-workspace,stitch-design}/plugin.json` (generated generic import view)
- Modify: `configs/claude/config/skill_policies.yml`
- Modify: `tests/bats/bundle_partition.bats`
- Create: `tests/python/manifest_agent/test_generate_plugin_views.py`

**Interfaces:**
- Consumes: `load_domain_contracts()` from Task 2 and the existing `[[skill:name]]` mapping semantics, ported out of `configs/claude/scripts/skill_ref.py`
- Produces: `render_views(repo_root: Path, check: bool) -> GenerationReport`

- [ ] **Step 1: Write failing generator invariants**

```python
def test_generator_emits_three_native_views_per_domain(repo_root, tmp_path):
    report = render_views(repo_root, output_root=tmp_path, check=False)
    assert len(report.bundles) == 9
    assert (tmp_path / "manifest-docs/.claude-plugin/plugin.json").is_file()
    assert (tmp_path / "manifest-docs/gemini-extension.json").is_file()
    assert (tmp_path / "manifest-docs/plugin.json").is_file()


def test_marketplace_excludes_optional_addon_from_parity_count(repo_root):
    contracts = load_domain_contracts(repo_root / "plugins")
    assert {c.name for c in contracts} == set(DOMAIN_BUNDLES)
```

- [ ] **Step 2: Run tests and verify missing contracts/generator**

Run: `uv run pytest tests/python/manifest_agent/test_generate_plugin_views.py -v`

Expected: FAIL because the nine contracts and generator do not exist.

- [ ] **Step 3: Add all nine contracts**

Use this complete structure in each bundle, changing only bundle metadata and declared capabilities:

```yaml
schema_version: 1
bundle:
  name: manifest-docs
  version: 0.2.0
  description: Documentation improvement, diagram generation, and doc-set orchestration.
  category: documentation
components:
  skills:
    root: skills
    include: ["*/SKILL.md"]
  agents: []
  hooks: []
  runtime: []
  guidance: []
capabilities:
  mcp:
    required: []
    default: []
    optional: []
  executables:
    required: [git, python3]
    default: []
    optional: []
compatibility:
  claude: {mode: native}
  codex: {mode: native}
  gemini: {mode: generated}
  cursor: {mode: generated}
  antigravity: {mode: imported}
  devin: {mode: native}
provenance:
  repository: https://github.com/RB-chrismandich/Manifest
  license: MIT
  license_file: LICENSE
  generated_by: tools/generate_plugin_views.py
```

Initial capability differences:

| Bundle | Required executables | Default capabilities | Optional capabilities |
|---|---|---|---|
| `manifest-code-quality` | `bash`, `git`, `python3` | none | `semgrep`, `playwright`, `browser-use` |
| `manifest-docs` | `git`, `python3` | none | none |
| `manifest-forge` | `bash`, `git`, `python3` | none | MCP `github`, `linear`, `atlassian`; executables `gh`, `glab` |
| `manifest-graphify` | `git` | executable `graphify` | none |
| `manifest-ops` | `bash`, `git`, `python3` | none | MCP `sentry`; executables `docker`, `tofu`, `terraform`, `tflint` |
| `manifest-security` | `bash`, `git`, `python3` | none | `semgrep` |
| `manifest-spec-planning` | `bash`, `git`, `python3` | none | executables `agy` |
| `manifest-workspace` | `bash`, `git`, `python3` | `context7` | `pass-cli` |
| `stitch-design` | `bash`, `git`, `python3` | executable `node` | MCP `stitch`; executable `chromium` |

- [ ] **Step 4: Implement deterministic rendering**

Generate:

```python
claude_view = {
    "name": contract.name,
    "version": contract.version,
    "description": contract.description,
    "skills": [f"./skills/{name}" for name in discovered_skill_names],
}
gemini_view = {"name": contract.name, "version": contract.version}
generic_view = {
    "name": contract.name,
    "version": contract.version,
    "description": contract.description,
    "skills": [f"skills/{name}" for name in discovered_skill_names],
    "required": [],
    "optional": [],
    "forbidden": [],
}
```

Render contract-declared agents, hooks, guidance, and runtime assets into each harness's documented native fields in addition to skills. When a harness cannot encode a component, emit a generated compatibility record naming that component as degraded; never omit the component from both the view and the compatibility report. Add fixture contracts containing one of every component type and assert each generated view either exposes it or records the exact degradation.

Port skill-reference parsing into `tools/skill_ref.py`; the generator must not import the future-deleted `configs/` tree. Sort all bundle and skill lists. `--check` writes nothing and prints every drifted path. Preserve the independent `adversarial-design-loop` marketplace entry unchanged, but never include it in the nine-domain parity total.

- [ ] **Step 5: Split domain and addon counts in the skill registry**

Replace the ambiguous single count with:

```yaml
domain_expected_total: 108
addon_expected_total: 6
expected_total: 114
```

Update `bundle_partition.bats` to assert the domain manifests equal `domain_expected_total`, the addon subtree equals `addon_expected_total`, and their sum equals `expected_total`.

- [ ] **Step 6: Generate and validate all views**

Run:

```bash
uv run python tools/generate_plugin_views.py
uv run python tools/generate_plugin_views.py --check
claude plugin validate --strict .claude-plugin/marketplace.json
gemini extensions validate plugins/manifest-docs
```

Expected: generator check is clean; Claude and representative Gemini validation pass.

- [ ] **Step 7: Run partition and generator tests**

Run: `uv run pytest tests/python/manifest_agent/test_generate_plugin_views.py -v && bats tests/bats/bundle_partition.bats`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add plugins .claude-plugin/marketplace.json configs/claude/config/skill_policies.yml tools/generate_plugin_views.py tools/skill_ref.py tests/bats/bundle_partition.bats tests/python/manifest_agent/test_generate_plugin_views.py
git commit -m "feat(plugins): generate native views from domain contracts"
```

---

### Task 4: Implement Immutable Release Acquisition, XDG Receipts, and Locking

**Files:**
- Create: `src/manifest_agent/process.py`
- Create: `src/manifest_agent/release.py`
- Create: `src/manifest_agent/state.py`
- Create: `tests/python/manifest_agent/test_process.py`
- Create: `tests/python/manifest_agent/test_release.py`
- Create: `tests/python/manifest_agent/test_state.py`

**Interfaces:**
- Consumes: `CommandResult`, `InstallationReceipt`, and `xdg_paths()` from Task 1
- Produces: `CommandRunner.run(argv, *, env=None)`, `resolve_release(selector) -> ResolvedRelease`, `installation_lock()`, `read_receipt()`, and `write_receipt_atomic()`

- [ ] **Step 1: Write failing process, checksum, and atomic-state tests**

```python
def test_runner_never_uses_a_shell(tmp_path):
    result = CommandRunner().run(("python3", "-c", "print('ok')"))
    assert result.stdout.strip() == "ok"
    assert result.argv[0] == "python3"


def test_checksum_mismatch_blocks_release(tmp_path):
    archive = tmp_path / "release.tgz"
    archive.write_bytes(b"tampered")
    with pytest.raises(ReleaseError, match="checksum mismatch"):
        verify_sha256(archive, "0" * 64)


def test_receipt_write_is_atomic_and_round_trips(tmp_path):
    write_receipt_atomic(tmp_path / "installation.json", SAMPLE_RECEIPT)
    assert read_receipt(tmp_path / "installation.json") == SAMPLE_RECEIPT
    assert not list(tmp_path.glob("*.tmp"))


def test_receipt_rejects_secret_fields(tmp_path):
    secret_entry = OwnedEntry(
        kind="mcp",
        identifier="context7",
        ownership_marker="manifest",
        target_path="Authorization: Bearer secret-value",
    )
    harness = replace(SAMPLE_RECEIPT.harnesses["claude"], owned_entries=(secret_entry,))
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": harness})
    with pytest.raises(StateError, match="credential material"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)
```

- [ ] **Step 2: Run tests and verify modules are absent**

Run: `uv run pytest tests/python/manifest_agent/test_process.py tests/python/manifest_agent/test_release.py tests/python/manifest_agent/test_state.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement argv-only subprocess execution**

```python
completed = subprocess.run(
    argv,
    check=False,
    capture_output=True,
    text=True,
    env=merged_env,
)
return CommandResult(
    tuple(argv), completed.returncode, completed.stdout, completed.stderr
)
```

Never accept a string command and never set `shell=True`.

- [ ] **Step 4: Implement immutable release resolution**

Support exactly two sources:

- `--source PATH` for a local checkout; require clean generated views, record its HEAD SHA plus dirty flag, and compute a deterministic tree digest into `archive_sha256` so reconcile can detect later local-source drift.
- the published release index at `https://github.com/RB-chrismandich/Manifest/releases/download/<version>/manifest-release.json`; require version, commit, archive URL, and SHA-256 for the archive.

Reject `main`, `master`, or another mutable branch name as an installation identity.

- [ ] **Step 5: Implement `fcntl` locking and atomic receipts**

Use `<state>/install.lock` with `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. Write JSON to a sibling temporary file opened with mode `0o600`, `fsync()`, then `os.replace()`. Reject owned-entry keys or values that serialize credential material, and redact native stderr before it reaches receipts or JSON reports. A partial result records verified harnesses and explicit failed operations without claiming failed capabilities.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest tests/python/manifest_agent/test_process.py tests/python/manifest_agent/test_release.py tests/python/manifest_agent/test_state.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/process.py src/manifest_agent/release.py src/manifest_agent/state.py tests/python/manifest_agent/test_process.py tests/python/manifest_agent/test_release.py tests/python/manifest_agent/test_state.py
git commit -m "feat(installer): add immutable releases and atomic state"
```

---

### Task 5: Define the Adapter Protocol and Hermetic Harness Stubs

**Files:**
- Create: `src/manifest_agent/adapters/__init__.py`
- Create: `src/manifest_agent/adapters/base.py`
- Create: `src/manifest_agent/adapters/registry.py`
- Create: `tests/fixtures/harness_bins/harness-stub`
- Create: `tests/python/manifest_agent/test_adapter_contract.py`

**Interfaces:**
- Consumes: `CommandRunner`, `DesiredState`, `HarnessResult`, and `ResultState`
- Produces: `HarnessAdapter`, `Detection`, `AdapterRegistry`, `verify_required_plugins()`, and `verify_declared_components()`

- [ ] **Step 1: Write the failing protocol contract test**

```python
@pytest.mark.parametrize(
    "name", ["claude", "codex", "gemini", "cursor", "antigravity", "devin"]
)
def test_registry_has_exact_supported_harnesses(name):
    assert AdapterRegistry.names() == (
        "claude",
        "codex",
        "gemini",
        "cursor",
        "antigravity",
        "devin",
    )


def test_nonzero_native_command_is_blocked(fake_adapter, desired):
    fake_adapter.runner.queue(returncode=9, stderr="native failure")
    result = fake_adapter.install(desired)
    assert result.state is ResultState.BLOCKED
    assert "native failure" in result.errors[0]


def test_missing_declared_component_cannot_be_ready(fake_adapter, desired):
    fake_adapter.inventory.omit("manifest-workspace:agent:executor")
    result = fake_adapter.inspect(desired)
    assert result.state is not ResultState.READY
    assert "manifest-workspace:agent:executor" in result.errors[0]
```

- [ ] **Step 2: Run the test and verify adapter imports fail**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the protocol and common helpers**

`base.py` must define the stable protocol from this plan's interface section plus:

```python
@dataclass(frozen=True)
class Detection:
    present: bool
    executable: str | None
    version: str | None
    reason: str | None = None
```

Common helpers convert any non-zero required native command into `BLOCKED`; default-capability failures become `DEGRADED`; optional failures are warnings only when explicitly selected.

Normalize every contract component to `<bundle>:<kind>:<stable-id>`. `verify_declared_components()` requires adapter evidence for each applicable skill, agent, hook, guidance block, runtime executable, and MCP/executable capability. A documented `degraded`/`unsupported` compatibility mode produces DEGRADED with its contract reason; missing evidence produces BLOCKED.

- [ ] **Step 4: Add the executable stub**

The stub reads `HARNESS_STUB_RESPONSES` JSON, appends argv as one JSON line to `HARNESS_STUB_LOG`, prints configured stdout/stderr, and exits with the configured code. It must never read the developer's real home.

- [ ] **Step 5: Run adapter contract tests**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_contract.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manifest_agent/adapters tests/fixtures/harness_bins tests/python/manifest_agent/test_adapter_contract.py
git commit -m "feat(installer): define harness adapter contract"
```

---

### Task 6: Implement Claude Code and Codex Native Marketplace Adapters

**Files:**
- Create: `src/manifest_agent/adapters/claude.py`
- Create: `src/manifest_agent/adapters/codex.py`
- Create: `tests/python/manifest_agent/test_adapter_claude.py`
- Create: `tests/python/manifest_agent/test_adapter_codex.py`

**Interfaces:**
- Consumes: Task 5 adapter protocol and Task 4 `ResolvedRelease`
- Produces: `ClaudeAdapter` and `CodexAdapter`

- [ ] **Step 1: Write exact argv tests**

```python
def test_claude_installs_marketplace_and_nine_plugins(adapter, desired, log):
    result = adapter.install(desired)
    assert result.state is ResultState.READY
    assert log[0] == [
        "claude",
        "plugin",
        "marketplace",
        "add",
        desired.source,
        "--scope",
        "user",
    ]
    assert [row[:3] for row in log if row[1:3] == ["plugin", "install"]] == [
        ["claude", "plugin", "install"]
    ] * 9


def test_codex_pins_marketplace_ref(adapter, desired, log):
    adapter.install(desired)
    assert log[0] == [
        "codex",
        "plugin",
        "marketplace",
        "add",
        desired.source,
        "--ref",
        desired.commit,
        "--json",
    ]
    assert ["codex", "plugin", "add", "manifest-docs@manifest", "--json"] in log
```

- [ ] **Step 2: Run tests and verify adapter modules are absent**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_claude.py tests/python/manifest_agent/test_adapter_codex.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement detection and user-scope install**

Claude commands:

```text
claude plugin marketplace add <source> --scope user
claude plugin install <bundle>@manifest --scope user
claude plugin list
```

Codex commands:

```text
codex plugin marketplace add <source> --ref <immutable-commit> --json
codex plugin add <bundle>@manifest --json
codex plugin list
```

Treat an already-present marketplace or plugin as idempotent only after `inspect()` confirms the selected version. Never parse success from prose alone when `--json` exists.

- [ ] **Step 4: Implement uninstall ownership**

Use only plugin IDs recorded in the receipt:

```text
claude plugin uninstall <bundle>@manifest
codex plugin remove <bundle>@manifest
```

Do not remove the marketplace if any unowned plugin still references it.

- [ ] **Step 5: Run adapter tests**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_claude.py tests/python/manifest_agent/test_adapter_codex.py -v`

Expected: PASS.

- [ ] **Step 6: Run isolated-home native smoke tests when CLIs are present**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_claude.py tests/python/manifest_agent/test_adapter_codex.py -m native -v`

Expected: each installed CLI validates the local marketplace without modifying the real home; absent CLIs produce an explicit `not present` test result, not a pass.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/adapters/claude.py src/manifest_agent/adapters/codex.py tests/python/manifest_agent/test_adapter_claude.py tests/python/manifest_agent/test_adapter_codex.py
git commit -m "feat(installer): add Claude and Codex adapters"
```

---

### Task 7: Implement Gemini CLI and Cursor Marketplace Adapters

**Files:**
- Create: `src/manifest_agent/adapters/gemini.py`
- Create: `src/manifest_agent/adapters/cursor.py`
- Create: `tests/python/manifest_agent/test_adapter_gemini.py`
- Create: `tests/python/manifest_agent/test_adapter_cursor.py`

**Interfaces:**
- Consumes: Task 5 adapter protocol and Task 3 generated views
- Produces: `GeminiAdapter` and `CursorAdapter`

- [ ] **Step 1: Write exact native-command tests**

```python
def test_gemini_installs_each_bundle_from_verified_release(adapter, desired, log):
    result = adapter.install(desired)
    assert result.state is ResultState.READY
    assert [row[:3] for row in log] == [["gemini", "extensions", "install"]] * 9
    assert all("--consent" in row and "--skip-settings" in row for row in log)


def test_cursor_indexes_immutable_marketplace_ref(adapter, desired, log):
    adapter.install(desired)
    assert log[0] == [
        "cursor-agent",
        "plugin",
        "marketplace",
        "add",
        desired.repository_url,
        "--git-ref",
        desired.commit,
    ]
```

- [ ] **Step 2: Run tests and verify adapter imports fail**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_gemini.py tests/python/manifest_agent/test_adapter_cursor.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement Gemini install and inspection**

For each verified release bundle directory:

```text
gemini extensions install <release>/plugins/<bundle> --consent --skip-settings
gemini extensions list
gemini skills list --all
```

Do not enable `--auto-update`; Manifest release consistency is coordinator-owned. `inspect()` requires the extension version and every contract-declared skill to appear.

- [ ] **Step 4: Implement Cursor marketplace indexing and verification**

Use the immutable Git commit because Cursor's marketplace CLI accepts Git URLs, not local paths:

```text
cursor-agent plugin marketplace add <repository-url> --git-ref <commit>
cursor-agent plugin marketplace list
```

The adapter then launches the installed CLI's documented plugin inventory probe against an isolated workspace and verifies all nine marketplace entries. If the current Cursor release indexes the marketplace but exposes no user-scope activation API, return `DEGRADED` with capability `plugins.activation=unsupported`; do not patch an undocumented Cursor database and do not introduce a shell wrapper. The live release gate in Task 17 remains red until Cursor exposes or confirms native activation.

Because Cursor installs from Git, reject a dirty `--source` checkout for Cursor instead of silently installing its clean HEAD. Published releases and clean local sources use the exact recorded commit.

- [ ] **Step 5: Implement owned uninstall**

Gemini uninstalls the nine recorded extension names. Cursor removes only the recorded Manifest marketplace URL:

```text
gemini extensions uninstall <bundle>
cursor-agent plugin marketplace remove <repository-url>
```

- [ ] **Step 6: Run adapter tests**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_gemini.py tests/python/manifest_agent/test_adapter_cursor.py -v`

Expected: PASS, including the explicit Cursor degraded branch.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/adapters/gemini.py src/manifest_agent/adapters/cursor.py tests/python/manifest_agent/test_adapter_gemini.py tests/python/manifest_agent/test_adapter_cursor.py
git commit -m "feat(installer): add Gemini and Cursor adapters"
```

---

### Task 8: Implement Antigravity and Devin Plugin Adapters

**Files:**
- Create: `src/manifest_agent/adapters/antigravity.py`
- Create: `src/manifest_agent/adapters/devin.py`
- Create: `tests/python/manifest_agent/test_adapter_antigravity.py`
- Create: `tests/python/manifest_agent/test_adapter_devin.py`

**Interfaces:**
- Consumes: Task 5 adapter protocol, generic `plugin.json` views from Task 3
- Produces: `AntigravityAdapter` and `DevinAdapter`

- [ ] **Step 1: Write exact install and verification tests**

```python
def test_antigravity_links_marketplace_then_installs_nine(adapter, desired, log):
    adapter.install(desired)
    assert log[0] == ["agy", "plugin", "link", "manifest", desired.source]
    assert [row[:3] for row in log[1:10]] == [["agy", "plugin", "install"]] * 9


def test_devin_installs_verified_local_bundle_views(adapter, desired, log):
    adapter.install(desired)
    assert log[0] == [
        "devin",
        "plugins",
        "install",
        str(desired.bundle_path("manifest-code-quality")),
        "--yes",
    ]
    assert len(log) == 10  # nine installs plus final list
```

- [ ] **Step 2: Run tests and verify adapter modules are absent**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_antigravity.py tests/python/manifest_agent/test_adapter_devin.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement Antigravity marketplace import**

Use only documented commands:

```text
agy plugin link manifest <verified-release-root>
agy plugin install <bundle>@manifest
agy plugin list
```

Validate each bundle before install with `agy plugin validate <bundle-path>`. A validation failure is `BLOCKED` and stops that harness before any install command.

- [ ] **Step 4: Implement Devin local-source installation**

Use the release archive already acquired and checksum-verified by Task 4:

```text
devin plugins install <verified-release-root>/plugins/<bundle> --yes
devin plugins list
devin plugins info <bundle>
```

Verify the installed version and discovered skills from `plugins info`; do not rely on `read_config_from.claude` or `~/.claude/skills` inheritance.

- [ ] **Step 5: Implement owned uninstall**

```text
agy plugin uninstall <bundle>
devin plugins remove <bundle>
devin plugins prune
```

Run `prune` only after all nine recorded bundles are removed; preserve plugins installed by other sources.

- [ ] **Step 6: Run adapter tests**

Run: `uv run pytest tests/python/manifest_agent/test_adapter_antigravity.py tests/python/manifest_agent/test_adapter_devin.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/adapters/antigravity.py src/manifest_agent/adapters/devin.py tests/python/manifest_agent/test_adapter_antigravity.py tests/python/manifest_agent/test_adapter_devin.py
git commit -m "feat(installer): add Antigravity and Devin adapters"
```

---

### Task 9: Merge Capability Declarations and Configure MCP Safely

**Files:**
- Create: `src/manifest_agent/capabilities.py`
- Create: `src/manifest_agent/data/mcp_catalog.yml`
- Create: `src/manifest_agent/data/executable_catalog.yml`
- Modify: `src/manifest_agent/adapters/base.py`
- Modify: `src/manifest_agent/adapters/claude.py`
- Modify: `src/manifest_agent/adapters/codex.py`
- Modify: `src/manifest_agent/adapters/gemini.py`
- Modify: `src/manifest_agent/adapters/cursor.py`
- Modify: `src/manifest_agent/adapters/antigravity.py`
- Modify: `src/manifest_agent/adapters/devin.py`
- Create: `tests/python/manifest_agent/test_capabilities.py`
- Create: `tests/python/manifest_agent/test_mcp_configuration.py`

**Interfaces:**
- Consumes: nine `BundleContract` objects
- Produces: `resolve_capabilities(contracts, selected_optional) -> CapabilityPlan` and adapter `apply_capabilities(plan)` methods

- [ ] **Step 1: Write failing union, conflict, and optional-selection tests**

```python
def test_repeated_default_mcp_is_registered_once(contracts):
    plan = resolve_capabilities(contracts, selected_optional=set())
    assert plan.default_mcp == ("context7",)


def test_optional_mcp_is_not_inferred(contracts):
    plan = resolve_capabilities(contracts, selected_optional=set())
    assert "github" not in plan.selected_mcp


def test_conflicting_transport_definitions_block():
    with pytest.raises(CapabilityConflict, match="context7"):
        merge_mcp_definitions(HTTP_CONTEXT7, STDIO_CONTEXT7)


def test_graphify_has_one_pinned_user_scope_recipe(executable_catalog):
    assert executable_catalog["graphify"] == {
        "manager": "uv-tool",
        "distribution": "graphifyy",
        "version": "0.9.31",
        "executable": "graphify",
    }
```

- [ ] **Step 2: Run tests and verify the capability module is absent**

Run: `uv run pytest tests/python/manifest_agent/test_capabilities.py tests/python/manifest_agent/test_mcp_configuration.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Add the coordinator-owned MCP transport catalog**

```yaml
context7:
  transport: http
  url: https://mcp.context7.com/mcp/oauth
github:
  transport: http
  url: https://api.githubcopilot.com/mcp/
linear:
  transport: http
  url: https://mcp.linear.app/mcp
atlassian:
  transport: http
  url: https://mcp.atlassian.com/v1/mcp
sentry:
  transport: http
  url: https://mcp.sentry.dev/mcp
stitch:
  transport: native-existing
  discovery_prefixes: [stitch, mcp_stitch]
```

The catalog contains no tokens, headers, client secrets, or credential literals. Auth remains native to each harness. `native-existing` means the coordinator verifies a user-selected, harness-provided integration but does not invent or persist an undocumented transport URL.

Add the executable catalog:

```yaml
graphify:
  manager: uv-tool
  distribution: graphifyy
  version: 0.9.31
  executable: graphify
```

Before committing this pin, re-query PyPI, inspect release files and licenses, and run the repository's dependency advisory check. `bash`, `git`, `python3`, and `node` are check-only system capabilities and never receive acquisition recipes. Optional executables without a reviewed recipe are `native-existing`: selection asks the adapter to verify them but does not run a guessed package-manager command.

- [ ] **Step 4: Implement tier resolution**

Required capability absence produces `BLOCKED`. Default capability failure produces `DEGRADED`. For a default or explicitly selected executable with a reviewed recipe, acquire it at user scope through the named manager, verify the executable/version, and record whether Manifest created the tool. `graphify` uses `uv tool install graphifyy==0.9.31`; uninstall removes it with `uv tool uninstall graphifyy` only when the receipt proves Manifest installed it. Preserve a matching pre-existing installation. Optional capability configuration occurs only when named by repeated `--with NAME` flags or selected interactively; non-interactive mode selects no optional capability.

- [ ] **Step 5: Implement native MCP operations**

Use native commands where available:

```text
claude mcp add --scope user --transport http context7 https://mcp.context7.com/mcp/oauth
codex mcp add context7 --url https://mcp.context7.com/mcp/oauth
gemini mcp add --scope user --transport http context7 https://mcp.context7.com/mcp/oauth
devin mcp add --scope user --transport http context7 https://mcp.context7.com/mcp/oauth
```

Cursor has no `mcp add`; merge only `mcpServers.manifest-context7` into `~/.cursor/mcp.json` with atomic JSON writes and receipt ownership. Antigravity uses its imported plugin's native MCP declaration when supported; otherwise report the exact MCP capability as degraded.

For catalog entries with `transport: native-existing`, inspect the harness's native tool inventory for one of the declared prefixes. Never synthesize a URL or credentials. When selected but absent, return an optional-capability warning naming the native setup the user must complete.

- [ ] **Step 6: Test preservation and idempotency**

Add fixtures containing unrelated MCP entries and assert byte-equivalent values remain after install and uninstall. With a fake `uv`, assert a missing default Graphify capability runs exactly `uv tool install graphifyy==0.9.31`, a matching pre-existing installation runs no install, and uninstall removes only the receipt-owned tool. Run:

`uv run pytest tests/python/manifest_agent/test_capabilities.py tests/python/manifest_agent/test_mcp_configuration.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/manifest_agent/capabilities.py src/manifest_agent/data/mcp_catalog.yml src/manifest_agent/data/executable_catalog.yml src/manifest_agent/adapters tests/python/manifest_agent/test_capabilities.py tests/python/manifest_agent/test_mcp_configuration.py
git commit -m "feat(installer): reconcile declared MCP capabilities"
```

---

### Task 10: Implement Install, Reconcile, Repair, and Uninstall Services

**Files:**
- Create: `src/manifest_agent/service.py`
- Modify: `src/manifest_agent/cli.py`
- Create: `tests/python/manifest_agent/test_service_install.py`
- Create: `tests/python/manifest_agent/test_service_reconcile.py`
- Create: `tests/python/manifest_agent/test_service_uninstall.py`

**Interfaces:**
- Consumes: release resolver, contracts, adapter registry, capability planner, locks, and receipts
- Produces: `ManifestService.install()`, `reconcile(apply=False)`, and `uninstall()` plus working Click commands

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_install_preserves_successful_harnesses_after_later_failure(service):
    service.adapters["claude"].result = READY_CLAUDE
    service.adapters["codex"].result = BLOCKED_CODEX
    report = service.install()
    assert report.state is ResultState.BLOCKED
    assert report.harnesses["claude"].state is ResultState.READY
    assert read_receipt().harnesses["claude"].verified is True


def test_reconcile_is_read_only_by_default(service):
    service.reconcile(apply=False)
    assert service.runner.calls == []


def test_uninstall_uses_receipt_not_directory_globs(service):
    service.uninstall()
    assert "foreign-plugin" not in service.removed_ids
```

- [ ] **Step 2: Run tests and verify service methods are absent**

Run: `uv run pytest tests/python/manifest_agent/test_service_install.py tests/python/manifest_agent/test_service_reconcile.py tests/python/manifest_agent/test_service_uninstall.py -v`

Expected: FAIL during import or with `not implemented`.

- [ ] **Step 3: Implement desired-state assembly and install ordering**

`install()` must: resolve release, load nine contracts, detect requested harnesses, acquire the lock, snapshot only files adapters declare, install all bundles, apply the capability union, inspect effective state, write partial or complete receipt, and return the aggregate verdict.

Use deterministic harness order:

```python
HARNESS_ORDER = ("claude", "codex", "gemini", "cursor", "antigravity", "devin")
```

- [ ] **Step 4: Implement read-only reconcile and `--apply` repair**

`reconcile()` compares receipt release/commit/checksums, nine plugin versions, declared skills, and capability state. `--apply` invokes only adapters whose inspection result is `DRIFTED` or `DEGRADED`; it must not reinstall already `READY` harnesses.

- [ ] **Step 5: Implement receipt-driven uninstall**

Uninstall adapters in reverse harness order, remove only recorded owned entries, retain a receipt when any removal fails, and delete the receipt only when every owned resource is gone.

- [ ] **Step 6: Wire Click options and structured output**

All commands support:

```text
--harness NAME    repeatable; default is detected supported harnesses
--source PATH     local verified checkout
--release VERSION immutable published release
--with NAME       repeatable optional capability selection
--non-interactive no prompts and no optional capabilities unless --with is present
--json            stable machine-readable report
```

`--harness all` converts every missing CLI into `BLOCKED`; default detection reports missing harnesses as notes outside the requested set.

- [ ] **Step 7: Run service and CLI tests**

Run: `uv run pytest tests/python/manifest_agent/test_service_*.py tests/python/manifest_agent/test_cli.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/manifest_agent/service.py src/manifest_agent/cli.py tests/python/manifest_agent/test_service_install.py tests/python/manifest_agent/test_service_reconcile.py tests/python/manifest_agent/test_service_uninstall.py tests/python/manifest_agent/test_cli.py
git commit -m "feat(installer): add convergent lifecycle commands"
```

---

### Task 11: Isolate `manifest-workspace` and Define Cross-Domain Skill Interfaces

**Files:**
- Create: `plugins/manifest-workspace/skills/parallel-agent/SKILL.md`
- Create: `plugins/manifest-workspace/skills/parallel-agent/scripts/parallel_agent.py`
- Create: `plugins/manifest-workspace/skills/parallel-agent/scripts/agents/` (bundle-local copy/refactor of the legacy agent package)
- Create: `plugins/manifest-workspace/skills/parallel-agent/config/parallel_agent.json`
- Create: `plugins/manifest-workspace/skills/parallel-agent/config/validation_criteria.json`
- Create: `plugins/manifest-workspace/skills/parallel-agent/references/orchestration.md`
- Create: `plugins/manifest-workspace/skills/parallel-agent/prompts/{synthesis,validation}.md`
- Create: `plugins/manifest-workspace/agents/orchestration/*.md`
- Create: `plugins/manifest-workspace/agents/devpanel/*.md`
- Create: `plugins/manifest-workspace/guidance/{orchestration,token-economy}.md`
- Create: `plugins/manifest-workspace/hooks/manifest-hooks.json`
- Create: `plugins/manifest-workspace/skills/learning-capture/scripts/learning_capture.py`
- Create: `plugins/manifest-workspace/skills/help/scripts/command_catalog.py`
- Create: `plugins/manifest-workspace/skills/help/catalog/commands.json` (generated release view)
- Create: `plugins/manifest-workspace/skills/env-check/scripts/env_check.py`
- Create: `plugins/manifest-workspace/skills/deploy-reconcile/scripts/plugin_reconcile.py`
- Modify: `plugins/manifest-workspace/skills/{config-audit,deploy-reconcile,env-check,help,learning-capture,metrics-report,pr-smoke,session-checkpoint,skill-evolve,test-isolate-ambient}/SKILL.md`
- Modify: `plugins/manifest-workspace/skills/ai-hooks-integration/SKILL.md`
- Modify: `plugins/manifest-workspace/skills/ai-hooks-integration/references/*.md`
- Modify: `plugins/manifest-workspace/skills/ai-hooks-integration/scripts/**/*.py`
- Modify: `plugins/manifest-workspace/skills/pr-smoke/scripts/run_pr_regression.sh`
- Modify: `plugins/manifest-workspace/manifest-capabilities.yml`
- Modify: `configs/claude/config/skill_policies.yml`
- Regenerate: `plugins/manifest-workspace/.claude-plugin/plugin.json`
- Regenerate: `plugins/manifest-workspace/gemini-extension.json`
- Regenerate: `plugins/manifest-workspace/plugin.json`
- Create: `tests/python/plugin_runtime/test_workspace_runtime.py`
- Create: `tests/bats/workspace_plugin_runtime.bats`

**Interfaces:**
- Consumes: XDG paths from Task 1 and the bundle-relative component model from Task 3
- Produces: `/manifest-workspace:parallel-agent`, `/manifest-workspace:learning-capture`, and bundle-local diagnostic commands that other domains invoke by skill name, never by file path

- [ ] **Step 1: Write failing workspace isolation tests**

```python
def test_parallel_agent_uses_only_files_below_its_skill_root(workspace_bundle):
    result = run_skill_script(
        workspace_bundle / "skills/parallel-agent/scripts/parallel_agent.py",
        "--help",
        home=empty_home(),
    )
    assert result.returncode == 0
    assert ".claude" not in result.stderr


def test_learning_capture_defaults_to_xdg_data(workspace_bundle, xdg_home):
    run_learning_capture(
        workspace_bundle, ["add", "--category", "pattern", "--text", "x"]
    )
    assert (xdg_home.data / "manifest/knowledge/entries.jsonl").is_file()


def test_workspace_contract_lists_every_runtime_asset(workspace_contract):
    runtime_paths = {
        component.path for component in workspace_contract.components.runtime
    }
    assert "skills/parallel-agent/scripts" in runtime_paths
    assert "skills/env-check/scripts" in runtime_paths
    assert workspace_contract.components.agents
    assert workspace_contract.components.hooks
    assert workspace_contract.components.guidance
```

Add a Bats case with an empty `HOME`, isolated XDG directories, `UV_NO_NETWORK=1`, and only fixture harness binaries on `PATH`. It must run `parallel_agent.py --help`, `command_catalog.py --all`, and `env_check.py --json` without reading the repository's `configs/claude` tree.

- [ ] **Step 2: Run the tests and verify legacy paths fail them**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_workspace_runtime.py -v
bats tests/bats/workspace_plugin_runtime.bats
```

Expected: FAIL because the new bundle-local commands do not exist and the current skills name `~/.claude` and `configs/claude` runtime files.

- [ ] **Step 3: Move the parallel-agent runtime into its own skill**

Refactor these legacy sources into `skills/parallel-agent/` without retaining imports back to `configs/claude`:

```text
configs/claude/scripts/parallel_agent.py       -> scripts/parallel_agent.py
configs/claude/scripts/agents/                 -> scripts/agents/
configs/claude/config/parallel_agent.yml       -> config/parallel_agent.json
configs/claude/config/validation_criteria.yml  -> config/validation_criteria.json
configs/claude/references/orchestration.md     -> references/orchestration.md
configs/claude/prompts/synthesis.md            -> prompts/synthesis.md
configs/claude/prompts/validation.md           -> prompts/validation.md
```

The script resolves these files from `Path(__file__).resolve().parents[1]`. Convert the immutable YAML registries to JSON and remove runtime `PyYAML` imports. It may invoke installed harness CLIs, but it may not install them, import `manifest_agent`, or assume a global `manifest` executable. JSON output keeps the legacy result schema so existing consumers retain capability parity.

- [ ] **Step 4: Replace shared-home workspace commands with bundle-local implementations**

Implement these storage and discovery rules:

| Skill | Bundle-local executable | Mutable state |
|---|---|---|
| `learning-capture` | `scripts/learning_capture.py` | `$XDG_DATA_HOME/manifest/knowledge/entries.jsonl` |
| `help` | `scripts/command_catalog.py` reading adjacent generated `catalog/commands.json` | none |
| `env-check` | `scripts/env_check.py` inspecting receipts and native harness inventories | `$XDG_STATE_HOME/manifest/installation.json` read-only |
| `deploy-reconcile` | `scripts/plugin_reconcile.py` comparing receipts/contracts/native inventories | none unless the user explicitly applies a repair through `uvx` |
| `metrics-report` | prompt-level analysis of `$XDG_STATE_HOME/manifest/agent-outputs/` | read-only |
| `session-checkpoint` | prompt-level write target | `$XDG_STATE_HOME/manifest/checkpoints/` |
| `skill-evolve` | scripts copied beside the skill | `$XDG_DATA_HOME/manifest/skill-evolve/` |

`deploy-reconcile` becomes an analysis skill; it must not invoke or require the ephemeral coordinator. Its structured result sets `repair_required: true` and names the drifted harness/capability, while installation documentation owns the separate repair command.

- [ ] **Step 5: Make cross-domain collaboration a skill contract**

Replace instructions that tell another domain to execute `manifest parallel-agent` or `~/.claude/scripts/learning_capture.sh` with qualified skill calls:

```markdown
Invoke `[[skill:parallel-agent]]` with the target files, mode, validation flag,
and timeout. Consume its JSON result when the current harness supports structured
skill output; otherwise perform the same review inline and report DEGRADED.

Invoke `[[skill:learning-capture]]` with category, language, and finding text.
Failure to capture learning is advisory and must not change the primary verdict.
```

Task 3's generator expands these references for each harness. No consumer may calculate a path into the `manifest-workspace` plugin.

- [ ] **Step 6: Make hook tooling harness-native without using Claude as shared storage**

Keep documented native targets such as `~/.claude/settings.json` only when the selected tool is Claude. Remove behavior where Cursor, Gemini, or OpenCode reads Claude settings. `tool_config.py` must return each tool's own settings path, and `install_all.py`/`remove_all.py` must merge only ownership-marked Manifest entries. Unsupported hook events return a structured degraded result.

- [ ] **Step 7: Package orchestration agents and standing guidance**

Move the reusable agent definitions from `configs/claude/agents/` and `configs/claude/agents-devpanel/` into the two workspace agent directories. Extract only current orchestration and token-economy behavior from the deploy-oriented Claude guide into bundle guidance. Declare stable IDs for every agent, guidance block, and workspace-owned hook. Generated adapters install native agent/rule/instruction forms where supported and record explicit degradation otherwise; copying prose into an unrelated harness settings file is not verification.

- [ ] **Step 8: Update the workspace contract and generated counts**

Extend `tools/generate_plugin_views.py` to build `skills/help/catalog/commands.json` from all nine contracts and discovered skill frontmatter, so runtime help never scans another installed plugin. Declare the new runtime directories and guidance files. Adding `parallel-agent` changes the domain skill count from 108 to 109 and the total including the independent addon from 114 to 115:

```yaml
domain_expected_total: 109
addon_expected_total: 6
expected_total: 115
```

Run `uv run python tools/generate_plugin_views.py` so all workspace views contain the new skill.

- [ ] **Step 9: Run workspace and generator tests**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_workspace_runtime.py tests/python/manifest_agent/test_generate_plugin_views.py -v
bats tests/bats/workspace_plugin_runtime.bats tests/bats/bundle_partition.bats
uv run python tools/generate_plugin_views.py --check
```

Expected: PASS with no access to a deployed home tree and exactly 109 domain skills.

- [ ] **Step 10: Commit**

```bash
git add plugins/manifest-workspace configs/claude/config/skill_policies.yml tests/python/plugin_runtime/test_workspace_runtime.py tests/bats/workspace_plugin_runtime.bats
git commit -m "refactor(workspace): make orchestration runtime bundle-local"
```

---

### Task 12: Move `manifest-forge` Runtime and Tracker Configuration Into Its Bundle

**Files:**
- Create: `plugins/manifest-forge/runtime/bin/{audit_log,auto_issue_dev,branch_clean,git_ops,git_platform,install_issue_hooks,issue_support,lifecycle,linear_ops,pr_review,tracker_ops}.sh`
- Create: `plugins/manifest-forge/runtime/python/tracker_registry.py`
- Create: `plugins/manifest-forge/runtime/config/{labels,review_bots,tracker_providers,tracker_triage}.json`
- Create: `plugins/manifest-forge/runtime/references/git-platform.md`
- Modify: `plugins/manifest-forge/skills/*/SKILL.md`
- Modify: `plugins/manifest-forge/skills/{issue-prioritize,issue-triage}/references/workflow.md`
- Modify: `plugins/manifest-forge/skills/issue-triage/README.md`
- Modify: `plugins/manifest-forge/skills/pr-monitor/references/{auto-trigger-hook,platform-commands}.md`
- Modify: `plugins/manifest-forge/skills/repo-clean/scripts/hygiene_gather.py`
- Modify: `plugins/manifest-forge/manifest-capabilities.yml`
- Regenerate: `plugins/manifest-forge/{.claude-plugin/plugin.json,gemini-extension.json,plugin.json}`
- Create: `tests/python/plugin_runtime/test_forge_runtime.py`
- Create: `tests/bats/forge_plugin_runtime.bats`

**Interfaces:**
- Consumes: `[[skill:parallel-agent]]` and `[[skill:learning-capture]]` from Task 11; native `git`, optional `gh`/`glab`, and selected tracker MCP capabilities
- Produces: a same-bundle `runtime/bin` command API used by Forge skills and XDG tracker state under `$XDG_STATE_HOME/manifest/forge/`

- [ ] **Step 1: Write failing runtime and provider tests**

```python
@pytest.mark.parametrize(
    "command",
    ["git_ops.sh", "tracker_ops.sh", "branch_clean.sh", "pr_review.sh", "lifecycle.sh"],
)
def test_forge_runtime_is_packaged_and_executable(forge_bundle, command):
    path = forge_bundle / "runtime/bin" / command
    assert path.is_file()
    assert os.access(path, os.X_OK)


def test_tracker_config_is_resolved_from_forge_bundle(forge_runtime, empty_home):
    result = forge_runtime("tracker_ops.sh", "resolve-provider", home=empty_home)
    assert result.returncode in (0, 3)
    assert ".claude/config" not in result.stderr
```

The Bats test must supply fake `git`, `gh`, `glab`, and `curl` commands and prove no command touches the real credential or home directories.

- [ ] **Step 2: Run tests and verify the missing bundle runtime**

Run: `uv run pytest tests/python/plugin_runtime/test_forge_runtime.py -v && bats tests/bats/forge_plugin_runtime.bats`

Expected: FAIL because Forge currently delegates to bootstrap-deployed scripts and configs.

- [ ] **Step 3: Refactor the legacy Forge scripts into one same-domain runtime**

Move behavior from the identically named files under `configs/claude/scripts/`. Every shell entry point sets its runtime root from its own file location:

```bash
FORGE_RUNTIME_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
FORGE_CONFIG_DIR="$FORGE_RUNTIME_DIR/config"
FORGE_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/manifest/forge"
```

Keep argv-based subprocess calls, explicit non-zero propagation, and current JSON schemas. `tracker_ops.sh` may call `linear_ops.sh` and `tracker_registry.py` only through paths below `FORGE_RUNTIME_DIR`; it may not inspect another plugin.

- [ ] **Step 4: Move immutable configuration and separate mutable overlays**

Package default provider, label, review-bot, and triage definitions as JSON in `runtime/config`; refactor `tracker_registry.py`, `branch_clean.sh`, and `lifecycle.sh` to use Python stdlib `json`. Read optional user overrides only from `$XDG_CONFIG_HOME/manifest/forge/*.json`, merge by stable identifier, reject unknown provider types, and never write credentials into either the bundle or receipt.

- [ ] **Step 5: Update every Forge instruction and hook reference**

Use instructions such as `run ../../runtime/bin/git_ops.sh relative to this skill's directory`; do not use `~/.claude`, `configs/claude`, `$CLAUDE_PLUGIN_ROOT`, or another harness-specific plugin-root variable. Replace parallel review and learning paths with the Task 11 qualified skill interfaces. Rewrite `pr-monitor` hook examples so the coordinator-installed ownership-marked hook invokes the packaged `pr_create_trigger.py` for the active harness.

- [ ] **Step 6: Declare and regenerate the Forge runtime**

Add `runtime/bin`, `runtime/python`, `runtime/config`, and `runtime/references` to the contract. Keep GitHub, Linear, and Atlassian MCP integrations optional and `gh`/`glab` optional. Run the generator.

- [ ] **Step 7: Run Forge compatibility tests**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_forge_runtime.py -v
bats tests/bats/forge_plugin_runtime.bats tests/bats/git_ops.bats tests/bats/tracker_ops.bats tests/bats/branch_clean.bats tests/bats/pr_review.bats tests/bats/lifecycle.bats
uv run python tools/generate_plugin_views.py --check
```

Expected: PASS; existing command semantics remain intact while all fixture paths resolve below the Forge bundle or XDG roots.

- [ ] **Step 8: Commit**

```bash
git add plugins/manifest-forge tests/python/plugin_runtime/test_forge_runtime.py tests/bats/forge_plugin_runtime.bats
git commit -m "refactor(forge): package git and tracker runtime"
```

---

### Task 13: Make `manifest-code-quality` and `manifest-docs` Self-Contained

**Files:**
- Create: `plugins/manifest-code-quality/skills/code-audit-constitution/scripts/constitution/`
- Create: `plugins/manifest-code-quality/skills/code-audit-constitution/scripts/constitution_check.py`
- Create: `plugins/manifest-code-quality/skills/code-audit-constitution/config/{code_constitution.json,constitution_baseline.json}`
- Create: `plugins/manifest-code-quality/skills/code-audit-constitution/references/{code-constitution.md,constitution/}`
- Create: `plugins/manifest-code-quality/skills/smoke-manage/scripts/smoke_orchestrator/`
- Create: `plugins/manifest-code-quality/skills/smoke-manage/scripts/smoke.py`
- Create: `plugins/manifest-code-quality/skills/smoke-manage/vendor/yaml/` (generated from the locked PyYAML source distribution)
- Create: `plugins/manifest-code-quality/skills/project-scaffold/templates/{python,go,node,terraform}/`
- Create: `plugins/manifest-code-quality/skills/code-audit/references/antipatterns.md`
- Create: `plugins/manifest-docs/runtime/docs_lint.py`
- Create: `plugins/manifest-docs/runtime/references/doc-concision.md`
- Create: `tools/vendor_bundle_dependencies.py`
- Modify: `plugins/manifest-code-quality/skills/*/SKILL.md`
- Modify: `plugins/manifest-docs/skills/*/SKILL.md`
- Modify: `plugins/manifest-code-quality/manifest-capabilities.yml`
- Modify: `plugins/manifest-docs/manifest-capabilities.yml`
- Regenerate: native views for both bundles
- Create: `tests/python/plugin_runtime/test_code_quality_runtime.py`
- Create: `tests/python/plugin_runtime/test_docs_runtime.py`
- Create: `tests/bats/code_quality_plugin_runtime.bats`
- Create: `tests/bats/docs_plugin_runtime.bats`

**Interfaces:**
- Consumes: Task 11 skill interfaces; required `git`/`python3`; selected optional scanners and browser tools
- Produces: standalone constitution, smoke-catalog, scaffold, and documentation lint capabilities

- [ ] **Step 1: Write failing executable and asset tests**

```python
def test_constitution_cli_loads_only_adjacent_policy(code_quality_bundle, empty_home):
    result = run_python(
        code_quality_bundle
        / "skills/code-audit-constitution/scripts/constitution_check.py",
        "--help",
        home=empty_home,
    )
    assert result.returncode == 0


def test_smoke_cli_imports_without_legacy_manifest_runtime(code_quality_bundle):
    result = run_python(
        code_quality_bundle / "skills/smoke-manage/scripts/smoke.py", "--help"
    )
    assert result.returncode == 0
    assert "manifest_cli" not in result.stderr


def test_docs_lint_runs_from_installed_bundle(docs_bundle, tmp_path):
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    result = run_python(
        docs_bundle / "runtime/docs_lint.py", str(tmp_path / "README.md")
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests and verify they fail on missing files**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_code_quality_runtime.py tests/python/plugin_runtime/test_docs_runtime.py -v
bats tests/bats/code_quality_plugin_runtime.bats tests/bats/docs_plugin_runtime.bats
```

Expected: FAIL because the scripts and policies still live under `configs/claude`.

- [ ] **Step 3: Co-locate constitution and smoke implementations with their skills**

Move the complete `constitution/` Python package, policy, baseline, language annexes, and CLI beside `code-audit-constitution`; convert its immutable policy to JSON and remove its `PyYAML` import. Move the complete `smoke_orchestrator/` package and its schemas beside `smoke-manage`; replace every `manifest smoke` example with the equivalent `python3 scripts/smoke.py` invocation relative to that skill. Preserve YAML catalog compatibility by packaging the pure-Python `yaml/` package from the exact PyYAML version and hashes in `uv.lock` under this skill's `vendor/` directory. `smoke.py` prepends only that adjacent vendor directory to `sys.path`. Preserve current exit codes: `0` success, `1` failed checks, `2` invalid input or missing required coverage.

`tools/vendor_bundle_dependencies.py` reads the locked PyYAML version and hashes, downloads into a temporary build directory, extracts only the pure-Python `yaml/` package plus its license, rejects native libraries and unexpected files, and supports `--check` by hashing the committed vendor tree. Network access is build-time only.

- [ ] **Step 4: Package scaffolds and audit references**

Copy the four top-level `templates/scaffold/*` trees into `project-scaffold/templates/`, update the skill to use only its adjacent copy, and add a byte-for-byte drift test until Task 18 deletes the top-level compatibility source. Copy `antipatterns.md` into the consuming code-audit skill. Replace learning-capture shell calls and parallel-agent process calls with the Task 11 skill interfaces.

- [ ] **Step 5: Package the docs linter and concision doctrine**

Move `docs_lint.py` and `doc-concision.md` into `plugins/manifest-docs/runtime/`. All four docs skills run that linter through a path relative to their own bundle and invoke `[[skill:parallel-agent]]` only when their existing dispatch threshold is met.

- [ ] **Step 6: Update contracts and generated views**

Declare every script, schema, template, and reference directory. Keep optional executable declarations explicit (`semgrep`, `playwright`, `browser-use`) and do not add them merely because prose mentions an optional workflow.

- [ ] **Step 7: Run migrated and legacy behavior tests**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_code_quality_runtime.py tests/python/plugin_runtime/test_docs_runtime.py -v
bats tests/bats/code_quality_plugin_runtime.bats tests/bats/docs_plugin_runtime.bats tests/bats/constitution_check.bats tests/bats/smoke_orchestrator_cli.bats tests/bats/docs_lint.bats
uv run python tools/vendor_bundle_dependencies.py --check
uv run python tools/generate_plugin_views.py --check
```

Expected: PASS with the migrated tests executing the plugin copies, not `configs/claude/scripts`.

- [ ] **Step 8: Commit**

```bash
git add plugins/manifest-code-quality plugins/manifest-docs tools/vendor_bundle_dependencies.py tests/python/plugin_runtime/test_code_quality_runtime.py tests/python/plugin_runtime/test_docs_runtime.py tests/bats/code_quality_plugin_runtime.bats tests/bats/docs_plugin_runtime.bats
git commit -m "refactor(quality): isolate audit smoke and docs runtimes"
```

---

### Task 14: Make `manifest-ops` and `manifest-security` Self-Contained

**Files:**
- Create: `plugins/manifest-ops/runtime/bin/{ci_platform,git_platform,version_pin}.sh`
- Create: `plugins/manifest-ops/runtime/config/version_pin.json`
- Create: `plugins/manifest-ops/runtime/references/ci/gitlab-ci-reproduction.md`
- Create: `plugins/manifest-security/runtime/bin/{ci_platform,git_platform}.sh`
- Create: `plugins/manifest-security/runtime/references/ci/gitlab-ci-triggers.md`
- Create: `plugins/manifest-security/runtime/references/{antipatterns,code-constitution}.md`
- Modify: `plugins/manifest-ops/skills/*/SKILL.md`
- Modify: `plugins/manifest-security/skills/*/SKILL.md`
- Modify: `plugins/manifest-ops/manifest-capabilities.yml`
- Modify: `plugins/manifest-security/manifest-capabilities.yml`
- Regenerate: native views for both bundles
- Create: `tests/python/plugin_runtime/test_ops_runtime.py`
- Create: `tests/python/plugin_runtime/test_security_runtime.py`
- Create: `tests/bats/ops_plugin_runtime.bats`
- Create: `tests/bats/security_plugin_runtime.bats`

**Interfaces:**
- Consumes: native CI files, `git`, `python3`, Task 11 skill interfaces, and explicit optional tools from each contract
- Produces: independent CI-platform detection and validation inside each bundle; neither domain imports the other's runtime

- [ ] **Step 1: Write failing isolated CI-helper tests**

```python
@pytest.mark.parametrize("bundle", ["manifest-ops", "manifest-security"])
def test_ci_platform_is_owned_by_each_consuming_bundle(
    plugin_root, bundle, fake_git_repo
):
    helper = plugin_root / bundle / "runtime/bin/ci_platform.sh"
    result = run(helper, cwd=fake_git_repo, home=empty_home())
    assert result.returncode == 0
    assert result.stdout.strip() in {"github", "gitlab", "unknown"}


def test_version_pin_does_not_require_home_hook(ops_bundle):
    result = run(ops_bundle / "runtime/bin/version_pin.sh", "--help", home=empty_home())
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests and verify shared helpers are still required**

Run: `uv run pytest tests/python/plugin_runtime/test_ops_runtime.py tests/python/plugin_runtime/test_security_runtime.py -v`

Expected: FAIL because both domains reference bootstrap-owned `ci_platform.sh`, and Ops references `version_pin.sh`/`version_pin_hook.sh` in the shared home.

- [ ] **Step 3: Copy the small CI boundary into each owning domain**

Create independent tested copies of `ci_platform.sh` and `git_platform.sh` in both bundles. This deliberate duplication avoids a cross-plugin runtime dependency. Keep their CLI behavior identical and add a comment naming the source test contract, not the other plugin path.

- [ ] **Step 4: Move Ops-only version pinning and CI reproduction assets**

Package `version_pin.sh`, a JSON conversion of its immutable rule registry, and the GitLab reproduction reference in Ops. Replace inline `yaml.safe_load` calls with stdlib JSON reads. Retire the global save hook as a required runtime; where a harness supports plugin hooks, declare an ownership-marked advisory invocation in the Ops contract. Harnesses without the hook expose the on-demand skill and report `hooks.version-pin=DEGRADED`, not READY-by-omission.

- [ ] **Step 5: Move Security-only trigger and doctrine assets**

Package GitLab trigger guidance, antipattern details, and the security-relevant constitution reference in Security. Replace learning queries and multi-agent review commands with Task 11 skill invocations. Keep Semgrep optional and fail only when the user selected it or a requested audit mode explicitly requires it.

- [ ] **Step 6: Update contracts with hooks and compatibility status**

Declare the version-pin hook in `manifest-ops` as a component with per-harness compatibility. Declare any security save hook similarly. The generated matrix must contain an explicit state for every hook/harness cell; an empty generated field is not verification.

- [ ] **Step 7: Run runtime, hook, and generator tests**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_ops_runtime.py tests/python/plugin_runtime/test_security_runtime.py -v
bats tests/bats/ops_plugin_runtime.bats tests/bats/security_plugin_runtime.bats tests/bats/ci_platform.bats tests/bats/version_pin.bats
uv run python tools/generate_plugin_views.py --check
```

Expected: PASS; both installed bundles operate with the other bundle absent.

- [ ] **Step 8: Commit**

```bash
git add plugins/manifest-ops plugins/manifest-security tests/python/plugin_runtime/test_ops_runtime.py tests/python/plugin_runtime/test_security_runtime.py tests/bats/ops_plugin_runtime.bats tests/bats/security_plugin_runtime.bats
git commit -m "refactor(plugins): isolate ops and security runtimes"
```

---

### Task 15: Isolate `manifest-spec-planning`, `manifest-graphify`, and `stitch-design`

**Files:**
- Create: `plugins/manifest-spec-planning/runtime/cddl/{cddl_invoke.py,cddl_loop.py}`
- Create: `plugins/manifest-spec-planning/runtime/spec_review.sh`
- Create: `plugins/manifest-spec-planning/runtime/prompts/cddl/*.md`
- Create: `plugins/manifest-spec-planning/runtime/prompts/{spec_review,spec_review_merge,spec_review_technical,synthesis}.md`
- Create: `plugins/manifest-spec-planning/runtime/references/{cddl-role-models,spec-artifact-discovery,sub-agent-dispatch}.md`
- Create: `plugins/manifest-spec-planning/runtime/config/{labels,review_models}.json`
- Create: `plugins/stitch-design/runtime/node/{package.json,package-lock.json}`
- Create: `plugins/stitch-design/runtime/node/build.mjs`
- Create: `plugins/stitch-design/runtime/dist/{extract-inline-html,post-process,snapshot,validate-react}.mjs` (generated standalone bundles)
- Modify: `plugins/manifest-spec-planning/skills/*/SKILL.md`
- Modify: `plugins/manifest-spec-planning/skills/spec-implement-loop/prompts/*.md`
- Modify: `plugins/manifest-spec-planning/manifest-capabilities.yml`
- Modify: `plugins/manifest-graphify/skills/graphify/SKILL.md`
- Modify: `plugins/manifest-graphify/manifest-capabilities.yml`
- Modify: `plugins/stitch-design/skills/*/SKILL.md`
- Modify: existing `plugins/stitch-design/skills/*/README.md`
- Modify: `plugins/stitch-design/skills/{extract-static-html,react-components,react-native}/scripts/*`
- Delete: `plugins/stitch-design/skills/react-components/{package.json,package-lock.json}` after generated validators replace their runtime dependencies
- Delete: `plugins/stitch-design/skills/react-native/package.json` after the generated validator replaces its runtime dependency
- Modify: `plugins/stitch-design/manifest-capabilities.yml`
- Regenerate: native views for all three bundles
- Create: `tests/python/plugin_runtime/test_spec_planning_runtime.py`
- Create: `tests/python/plugin_runtime/test_graphify_runtime.py`
- Create: `tests/python/plugin_runtime/test_stitch_runtime.py`
- Create: `tests/bats/spec_planning_plugin_runtime.bats`

**Interfaces:**
- Consumes: Task 11 parallel review, bundle-local CDDL/spec-review assets, default coordinator-managed Graphify executable, and selected Stitch MCP
- Produces: XDG-backed plan lifecycle and self-contained design/review workflows

- [ ] **Step 1: Write failing spec runtime and independence tests**

```python
def test_cddl_cli_resolves_adjacent_charter(spec_bundle, empty_home):
    result = run_python(
        spec_bundle / "runtime/cddl/cddl_invoke.py",
        "--charter",
        "qa-critic",
        "--help",
        home=empty_home,
    )
    assert result.returncode == 0


def test_default_plan_store_is_xdg(spec_bundle, xdg_home):
    assert resolve_plan_root({}) == xdg_home.data / "manifest/plans"


def test_graphify_and_stitch_do_not_require_workspace_files(plugin_root):
    assert no_cross_plugin_paths(plugin_root / "manifest-graphify")
    assert no_cross_plugin_paths(plugin_root / "stitch-design")
```

- [ ] **Step 2: Run tests and verify current home/repository references fail**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_spec_planning_runtime.py tests/python/plugin_runtime/test_graphify_runtime.py tests/python/plugin_runtime/test_stitch_runtime.py -v
bats tests/bats/spec_planning_plugin_runtime.bats
```

Expected: FAIL because spec planning loads `~/.claude/prompts`, `~/.claude/scripts`, `~/.claude/.plans`, and repository `configs/claude` assets.

- [ ] **Step 3: Package CDDL and spec-review assets**

Move the CDDL invoker/loop, all role charters, spec artifact discovery, and spec-review prompts into `runtime/`. Resolve named charters against `runtime/prompts/cddl`; reject `..`, absolute paths, and unknown charter names. Convert model and label defaults to JSON so `spec_review.sh` uses Python stdlib only. `spec_review.sh` invokes `agy` or another selected native reviewer directly and returns non-zero on unverifiable output.

- [ ] **Step 4: Move plan state from Claude home to XDG data**

Use `${XDG_DATA_HOME:-$HOME/.local/share}/manifest/plans` with `.archive/` and `.abandoned/` children. A project may opt into a committed local plan root through `.manifest/plans.yml`; no skill writes project files without that explicit repository setting. Tracker label operations use the Forge skill interface rather than `git_ops.sh` path access.

- [ ] **Step 5: Remove remaining Graphify and Stitch shared-path assumptions**

Graphify invokes the default `graphify` executable acquired by Task 9 and stores only its own cache below `$XDG_CACHE_HOME/manifest/graphify`. If acquisition failed, the bundle remains installed but its capability is explicitly DEGRADED. Stitch review steps invoke `[[skill:parallel-agent]]` rather than a shell command. `stitch` remains optional unless the user invokes a mode that explicitly requires remote Stitch access.

Replace runtime `npm`/`npx` assumptions with checked release artifacts. Pin exact build-time versions of `esbuild`, Babel parser/traverse/generator, and `puppeteer-core` in `runtime/node/package-lock.json` after verifying registry existence, maintenance, licenses, and advisories. `build.mjs` emits four self-contained `.mjs` files, includes dependency license notices, and supports `--check` by rebuilding in a temporary directory and comparing hashes. Do not ship `node_modules`. Snapshot execution uses a contract-declared optional `chromium` executable and reports it missing without downloading a browser. Rewrite the React and React Native validators to use the generated pure-JavaScript parser bundle instead of platform-specific `@swc/core`.

Update every Stitch skill/README to resolve same-bundle skills by qualified skill name and generated scripts relative to the current skill. Remove references to external `stitch-utilities`, `stitch-skills/plugins`, global `npx skills add`, and obsolete per-skill package manifests.

- [ ] **Step 6: Update contracts and regenerate views**

Declare Spec Planning runtime prompts/references/config, Graphify cache/executable behavior, and all Stitch script/package assets. Add optional executable `chromium` to Stitch. The generator must include package lockfiles, generated `.mjs` files, and runtime files in release checksums.

- [ ] **Step 7: Run focused and cross-domain-absence tests**

Run:

```bash
uv run pytest tests/python/plugin_runtime/test_spec_planning_runtime.py tests/python/plugin_runtime/test_graphify_runtime.py tests/python/plugin_runtime/test_stitch_runtime.py -v
bats tests/bats/spec_planning_plugin_runtime.bats tests/bats/spec_review.bats
(cd plugins/stitch-design/runtime/node && npm ci --ignore-scripts && node build.mjs --check)
uv run python tools/generate_plugin_views.py --check
```

Expected: PASS when each tested bundle is copied alone into a temporary directory; Stitch runtime tests remove `node_modules`, disable network access, and execute the generated validators successfully.

- [ ] **Step 8: Commit**

```bash
git add plugins/manifest-spec-planning plugins/manifest-graphify plugins/stitch-design tests/python/plugin_runtime/test_spec_planning_runtime.py tests/python/plugin_runtime/test_graphify_runtime.py tests/python/plugin_runtime/test_stitch_runtime.py tests/bats/spec_planning_plugin_runtime.bats
git commit -m "refactor(plugins): isolate planning graph and design assets"
```

---

### Task 16: Inventory Legacy Ownership and Implement the One-Writer Migration

**Files:**
- Create: `src/manifest_agent/data/legacy_inventory.yml`
- Create: `src/manifest_agent/migration.py`
- Modify: `src/manifest_agent/models.py`
- Modify: `src/manifest_agent/service.py`
- Modify: `src/manifest_agent/cli.py`
- Create: `tools/render_capability_inventory.py`
- Create: `docs/PLUGIN_CAPABILITY_INVENTORY.md` (generated)
- Create: `tests/fixtures/legacy_homes/bootstrap-managed/`
- Create: `tests/fixtures/legacy_homes/mixed-user-state/`
- Create: `tests/python/manifest_agent/test_legacy_inventory.py`
- Create: `tests/python/manifest_agent/test_migration.py`
- Create: `tests/bats/plugin_migration.bats`

**Interfaces:**
- Consumes: Task 10 lifecycle service, nine self-contained bundles, receipts, adapter snapshots, and the exact bootstrap output inventory
- Produces: `MigrationService.migrate(desired: DesiredState) -> OperationReport`, `scan_legacy_state(paths: XdgPaths) -> LegacySnapshot`, and the working `manifest migrate` command

- [ ] **Step 1: Write the failing inventory completeness tests**

```python
def test_every_bootstrap_output_class_has_a_disposition(legacy_inventory):
    assert set(legacy_inventory.categories) == {
        "skills",
        "agents",
        "guidance",
        "hooks",
        "permissions",
        "mcp",
        "scripts",
        "optional_tools",
        "configuration",
        "diagnostics",
        "updates",
        "uninstall",
    }


def test_destructive_entries_require_ownership_proof(legacy_inventory):
    for entry in legacy_inventory.entries:
        if entry.action in {"disable", "remove"}:
            assert entry.ownership_proof.type in {
                "symlink-target",
                "deploy-stamp",
                "generated-hash",
                "exact-marker",
            }


def test_unknown_files_are_always_user_owned(scan_result):
    assert scan_result.entry("~/.claude/custom.txt").classification == "user-owned"
```

- [ ] **Step 2: Write failing handoff and rollback tests**

```python
def test_migration_never_exposes_zero_or_two_writers(migration, event_log):
    migration.migrate(DESIRED)
    assert event_log == [
        "snapshot-legacy",
        "shadow-install",
        "shadow-verify",
        "disable-legacy",
        "native-install",
        "native-verify",
        "commit-receipt",
    ]


def test_failed_native_verify_restores_legacy_writer(migration, legacy_home):
    migration.adapters["claude"].verify_result = BLOCKED_CLAUDE
    report = migration.migrate(DESIRED)
    assert report.state is ResultState.BLOCKED
    assert legacy_home.skills_link.is_symlink()
    assert not migration.receipt_path.exists()


def test_migration_preserves_unowned_settings(migration, mixed_user_home):
    before = mixed_user_home.read_unowned_entries()
    migration.migrate(DESIRED)
    assert mixed_user_home.read_unowned_entries() == before
```

- [ ] **Step 3: Run tests and verify migration is not implemented**

Run:

```bash
uv run pytest tests/python/manifest_agent/test_legacy_inventory.py tests/python/manifest_agent/test_migration.py -v
bats tests/bats/plugin_migration.bats
```

Expected: FAIL because `migrate` still raises the deliberate Task 1 `ClickException` and there is no authoritative inventory.

- [ ] **Step 4: Add the machine-readable ownership inventory**

Each entry must contain:

```yaml
- id: claude-shared-skills
  category: skills
  path: ~/.claude/skills
  classification: bundle-owned
  destination: native-plugin-managers
  ownership_proof:
    type: symlink-target
    value: ~/.manifest/skills
  action: disable
  recovery: restore-symlink
```

Include every bootstrap service, home mirror, symlink hub, deployed script/config/reference/prompt/agent tree, generated Cursor rule/agent file, MCP ownership marker, hook, permissions merge, optional dependency, deploy stamp, update path, and uninstall path. Classify credentials and unrecognized settings as `user-owned`; classify the ephemeral coordinator, release metadata, lock, and receipt as `coordinator-owned`; classify native credential stores as `harness-native`; explicitly name retired capabilities instead of omitting them.

- [ ] **Step 5: Render and review the human inventory**

`tools/render_capability_inventory.py --check` generates one row per entry with legacy source, classification, bundle/native destination, ownership proof, migration action, recovery action, and parity test. It fails if a destination references `manifest-core`, bootstrap, or an unqualified shared plugin path.

- [ ] **Step 6: Implement shadow verification and the one-writer handoff**

For each requested harness:

1. Snapshot only inventoried, ownership-proven paths into `$XDG_STATE_HOME/manifest/migration-backups/<timestamp>/` with mode, link target, SHA-256, and a recovery manifest.
2. Install the selected release into an adapter-created isolated home and verify all nine bundles and declared capabilities.
3. Atomically rename or unlink only proven legacy writers for that harness.
4. Install into the real native manager and verify effective state.
5. On failure, uninstall the incomplete native copy, restore the exact snapshot, and leave the legacy writer active.
6. On success, remove only inventoried legacy outputs and write the native receipt plus recovery location.

Never run native and legacy copies in a live agent session. Refuse migration when a supported harness process has an open lock or when ownership proof is ambiguous; name the exact path requiring user action.

- [ ] **Step 7: Implement recovery and idempotency**

The backup directory contains a standalone `restore.py` and `recovery.json`; `restore.py` uses only Python stdlib and never imports or executes retired bootstrap code. A second `manifest migrate` against a completed native receipt returns READY without mutations. A partial prior migration resumes from the recorded per-harness phase after re-verifying the snapshot.

- [ ] **Step 8: Wire `manifest migrate` output and repair guidance**

Support the same release, harness, optional capability, non-interactive, and JSON flags as install. Every partial failure prints an exact next command, for example:

```text
uvx --from manifest-agent manifest migrate --release 0.2.0 --harness codex --non-interactive
```

Do not mark shadow-only success as an installed receipt.

- [ ] **Step 9: Run inventory, migration, and lifecycle tests**

Run:

```bash
uv run python tools/render_capability_inventory.py --check
uv run pytest tests/python/manifest_agent/test_legacy_inventory.py tests/python/manifest_agent/test_migration.py tests/python/manifest_agent/test_service_*.py -v
bats tests/bats/plugin_migration.bats
```

Expected: PASS for fresh bootstrap-managed, mixed user state, rollback, resume, and repeated migration fixtures.

- [ ] **Step 10: Commit**

```bash
git add src/manifest_agent/data/legacy_inventory.yml src/manifest_agent/migration.py src/manifest_agent/models.py src/manifest_agent/service.py src/manifest_agent/cli.py tools/render_capability_inventory.py docs/PLUGIN_CAPABILITY_INVENTORY.md tests/fixtures/legacy_homes tests/python/manifest_agent/test_legacy_inventory.py tests/python/manifest_agent/test_migration.py tests/bats/plugin_migration.bats
git commit -m "feat(installer): migrate bootstrap ownership atomically"
```

---

### Task 17: Enforce Zero Legacy Runtime Paths, Offline Operation, and Live Six-Harness Parity

**Files:**
- Create: `tools/check_plugin_runtime_paths.py`
- Create: `tools/render_plugin_capability_matrix.py`
- Create: `docs/PLUGIN_CAPABILITY_MATRIX.md` (generated)
- Create: `tests/python/test_plugin_runtime_paths.py`
- Create: `tests/python/manifest_agent/test_offline_installation.py`
- Create: `tests/python/manifest_agent/test_concurrent_operations.py`
- Create: `tests/python/manifest_agent/test_partial_failure_repair.py`
- Create: `tests/bats/plugin_offline_runtime.bats`
- Create: `tests/bats/plugin_native_parity.bats`
- Create: `.github/workflows/plugin-parity-live.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `tools/generate_plugin_views.py`

**Interfaces:**
- Consumes: all contracts, generated views, adapters, bundle-local runtimes, migration receipts, and isolated/live harness inventory
- Produces: release-blocking static, offline, concurrency, preservation, and six-harness parity evidence

- [ ] **Step 1: Write the failing zero-path gate**

The checker scans every runtime-bearing contract path and all skill instructions. It rejects executable or instructional dependencies matching:

```python
FORBIDDEN_RUNTIME_PATTERNS = (
    "bootstrap.sh",
    "bootstrap/",
    "~/.claude/scripts",
    "~/.claude/config",
    "configs/claude/scripts",
    "configs/claude/config",
    "configs/claude/prompts",
    "configs/claude/references",
    "manifest-agent",
    "uvx --from manifest-agent",
    "manifest parallel-agent",
    "manifest smoke",
    "../manifest-",
    "npx skills add",
    "stitch-skills/plugins",
    "stitch-utilities",
)
```

Allow native harness-owned settings or transcript paths only through an explicit allowlist keyed by bundle, capability, and harness; for example, Claude hook configuration may name `~/.claude/settings.json`, while no Cursor or Gemini capability may use it.

The same checker parses Python imports, Node import specifiers, shell `command -v` probes, and direct external command calls in runtime components. It permits Python stdlib, an adjacent declared `vendor/` tree, Node built-ins, shell built-ins, and imports already bundled into a generated `.mjs`; every other runtime dependency must appear in the owning contract and have an offline or explicit-degradation test.

- [ ] **Step 2: Run the gate and capture every remaining violation**

Run: `uv run python tools/check_plugin_runtime_paths.py --json`

Expected: FAIL and list any missed file from Tasks 11-15 by exact path and line. Fix every violation in its owning bundle before proceeding; do not add broad directory exemptions.

- [ ] **Step 3: Add offline installed-bundle tests**

Install all nine bundles through each fake adapter into isolated homes, delete the unpacked coordinator release and remove `uv`, `uvx`, repository paths, and network tools from `PATH`, then execute one representative local capability from every bundle. Set `UV_NO_NETWORK=1`; monkeypatch Python sockets to raise; make fixture `curl`, `npm`, and `npx` fail with `network disabled`. Remote-purpose capabilities such as GitHub, Linear, Context7, or Stitch are excluded from local execution but must return a precise offline error when invoked.

- [ ] **Step 4: Add concurrency, partial-failure, rollback, and preservation tests**

Cover:

- two simultaneous install/migrate/reconcile-apply operations, with exactly one lock winner;
- process interruption between temporary write, `fsync`, and `os.replace`;
- one harness failing after another reaches READY;
- rollback of the current harness without rolling back verified unrelated harnesses;
- `reconcile --apply` repairing only DEGRADED/DRIFTED harnesses;
- byte-equivalent preservation of unowned plugins, hooks, MCP entries, rules, permissions, and settings; and
- uninstall retaining the receipt until every owned resource is removed.

Skipped fixture commands and missing verification output must produce BLOCKED test results.

- [ ] **Step 5: Generate the capability matrix from evidence**

`tools/render_plugin_capability_matrix.py` joins contract component IDs with adapter inspection results. The generated document contains one row per bundle capability and one column per harness, with only `READY`, `DEGRADED(reason)`, `BLOCKED(reason)`, or `N/A(contract reason)`. A blank cell, skipped probe, unknown version, or unverified executable blocks `--check`.

- [ ] **Step 6: Add isolated native parity tests**

For each installed local CLI, create an isolated home and run the adapter's real validate/install/list/info/uninstall sequence against the local release. An absent CLI yields a reported BLOCKED probe in developer runs; it is not silently skipped. Assert that emdash has no adapter or config tree because it inherits whichever supported harness it launches.

- [ ] **Step 7: Add the live release-blocking workflow**

Create a six-entry matrix:

```yaml
matrix:
  harness: [claude, codex, gemini, cursor, antigravity, devin]
```

Each job installs its harness through the workflow's licensed/secret-backed setup, builds the `manifest-agent` wheel and immutable release archive, then runs:

```bash
uvx --from "$WHEEL" manifest install --source "$GITHUB_WORKSPACE" \
  --harness "$HARNESS" --non-interactive --json
uvx --from "$WHEEL" manifest reconcile --source "$GITHUB_WORKSPACE" \
  --harness "$HARNESS" --json
uvx --from "$WHEEL" manifest uninstall --harness "$HARNESS" --json
```

Upload the JSON report and isolated home as diagnostic artifacts after redacting native credential stores. Require READY for every applicable contract capability. Cursor's documented activation gap remains a failing release check until the adapter can verify native user-scope activation; do not waive it with `continue-on-error`.

- [ ] **Step 8: Wire all static gates into normal CI**

Add jobs for schema validation, generated-view drift, vendored-dependency drift/license checks, runtime-path scanning, inventory drift, capability-matrix drift, Python tests, Bats plugin tests, wheel build, and release archive checksum verification. The normal PR workflow may use fake adapters; the live workflow is a protected release requirement.

- [ ] **Step 9: Run the complete local parity suite**

Run:

```bash
uv run python tools/generate_plugin_views.py --check
uv run python tools/vendor_bundle_dependencies.py --check
(cd plugins/stitch-design/runtime/node && npm ci --ignore-scripts && node build.mjs --check)
uv run python tools/check_plugin_runtime_paths.py
uv run python tools/render_capability_inventory.py --check
uv run python tools/render_plugin_capability_matrix.py --check
uv run pytest tests/python -v
bats tests/bats/bundle_partition.bats tests/bats/plugin_offline_runtime.bats tests/bats/plugin_migration.bats tests/bats/plugin_native_parity.bats
uv build
```

Expected: every local check passes. If a live CLI is absent, the local native report names it BLOCKED; only the protected workflow can satisfy the six-harness release verdict.

- [ ] **Step 10: Commit**

```bash
git add tools/check_plugin_runtime_paths.py tools/render_plugin_capability_matrix.py docs/PLUGIN_CAPABILITY_MATRIX.md tests/python/test_plugin_runtime_paths.py tests/python/manifest_agent/test_offline_installation.py tests/python/manifest_agent/test_concurrent_operations.py tests/python/manifest_agent/test_partial_failure_repair.py tests/bats/plugin_offline_runtime.bats tests/bats/plugin_native_parity.bats .github/workflows/plugin-parity-live.yml .github/workflows/ci.yml tools/generate_plugin_views.py
git commit -m "test(plugins): gate offline six-harness parity"
```

---

### Task 18: Retire Bootstrap, Shared Home Trees, and Legacy Release Machinery

**Files:**
- Delete: `bootstrap.sh`
- Delete: `bootstrap/`
- Delete: `configs/`
- Delete: `.apm/`
- Delete: `templates/` after the scaffold source moves into `manifest-code-quality`
- Delete: bootstrap/deploy/APM mirror Bats tests superseded by Tasks 11-17
- Delete: legacy runtime packaging and home-deploy workflow steps from `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `tools/build_manifest_release.py`
- Create: `docs/MIGRATION_RECOVERY.md`
- Create: `docs/legacy/BOOTSTRAP_RETIREMENT.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/README.md`
- Modify: `docs/GETTING_STARTED.md`
- Modify: `docs/CONFIGURATION.md`
- Modify: `docs/ARCHITECTURE_DIAGRAMS.md`
- Modify: `docs/EMDASH.md`
- Modify: `.gitignore`
- Modify: `.pre-commit-config.yaml`
- Modify: `pyproject.toml`
- Modify: tests that still assert bootstrap or home-mirror behavior

**Interfaces:**
- Consumes: a green Task 17 protected parity workflow and a published/testable `manifest-agent` wheel
- Produces: the final bootstrap-free repository, immutable release artifacts, PyPI publication, and documented stdlib-only migration recovery

- [ ] **Step 1: Write the failing retirement and release-artifact tests**

```python
def test_repository_has_no_deployment_tree(repo_root):
    assert not (repo_root / "bootstrap.sh").exists()
    assert not (repo_root / "bootstrap").exists()
    assert not (repo_root / "configs").exists()
    assert not (repo_root / ".apm").exists()
    assert not (repo_root / "templates").exists()


def test_release_index_covers_all_bundle_bytes(release_index, release_archive):
    assert release_index.version == "0.2.0"
    assert set(release_index.bundles) == set(DOMAIN_BUNDLES)
    assert release_index.archive_sha256 == sha256(release_archive)


def test_docs_use_uvx_install_entrypoint(repo_root):
    assert (
        "uvx --from manifest-agent manifest install"
        in (repo_root / "README.md").read_text()
    )
```

- [ ] **Step 2: Prove the new path is green before deleting legacy code**

Require a successful protected `plugin-parity-live.yml` run for the exact commit being retired. Locally run Task 17's full suite plus `uv build`. Stop if any harness capability is DEGRADED or BLOCKED; bootstrap deletion is not allowed while parity depends on it.

- [ ] **Step 3: Build immutable release artifacts**

`tools/build_manifest_release.py` must:

1. validate the nine contracts and generated native views;
2. verify the vendored Python and generated Stitch runtime hashes, then reject a dirty tree or mismatched bundle versions;
3. generate a release-only marketplace containing exactly the nine domain entries, then produce a deterministic `manifest-plugins-<version>.tar.gz` containing that marketplace and exactly the nine domain bundles;
4. compute per-file and archive SHA-256 values;
5. emit `manifest-release.json` with version, source commit, archive URL, archive checksum, bundle checksums, schema version, and minimum adapter versions; and
6. exclude `adversarial-design-loop` unless an independent addon release explicitly requests it.

The release workflow publishes the wheel to PyPI as `manifest-agent`, uploads the archive/index/checksums to the matching GitHub release, then runs the protected live install from the published artifacts rather than the checkout.

- [ ] **Step 4: Remove the bootstrap and mirror source trees**

Delete `bootstrap.sh`, `bootstrap/`, `configs/`, `.apm/`, and the superseded top-level `templates/` tree only after every surviving runtime/config/reference/template has a tested owner under `plugins/`, `src/manifest_agent/data/`, or repository-only guidance. Remove symlink-generation, home-copy, service-toggle, legacy Manifest CLI, APM mirror, deploy stamp, and bootstrap uninstall code rather than leaving compatibility shims.

- [ ] **Step 5: Remove superseded tests and keep equivalent coverage**

Delete tests whose subject no longer exists, including `bootstrap_*.bats`, `deploy_*.bats`, `apm_*.bats`, mirror-generation tests, legacy `manifest_wrapper.bats`, and home-runtime tests. Before deleting each behavior test, map it to the capability inventory's parity-test field and an existing Task 11-17 replacement. Keep any test that validates still-supported bundle behavior by retargeting it to the bundle-local executable.

- [ ] **Step 6: Rewrite installation, configuration, update, and removal docs**

The primary flow becomes:

```bash
uvx --from manifest-agent manifest install
uvx --from manifest-agent manifest migrate
uvx --from manifest-agent manifest reconcile
uvx --from manifest-agent manifest uninstall
```

Document user-scope default detection, `--harness all`, optional `--with`, XDG receipt/state locations, offline operation, native update ownership, partial convergence, Cursor activation status, and the fact that emdash is not a target. Remove all instructions to deploy, copy, symlink, update, repair, or uninstall through bootstrap.

- [ ] **Step 7: Preserve history and standalone recovery without executable bootstrap code**

`docs/legacy/BOOTSTRAP_RETIREMENT.md` records the former architecture, retirement release, and inventory link. `docs/MIGRATION_RECOVERY.md` explains how to run the generated backup's stdlib-only `restore.py`, inspect checksums, and recover from an interrupted handoff. Neither document tells users to execute deleted bootstrap code.

- [ ] **Step 8: Update repository guidance and development gates**

Describe `plugins/*/manifest-capabilities.yml` as the source of truth, generated native views as checked artifacts, and `uv run`/`uv build` as the development workflow. Remove AGENTS/CLAUDE claims that skills come from `.apm`, that configs deploy to assistant homes, or that a permanent `manifest` CLI exists. Keep repository-local agent guidance separate from user-scope plugin distribution.

- [ ] **Step 9: Run retirement scans and the complete test suite**

Run:

```bash
test ! -e bootstrap.sh
test ! -e bootstrap
test ! -e configs
test ! -e .apm
test ! -e templates
uv run python tools/vendor_bundle_dependencies.py --check
uv run python tools/check_plugin_runtime_paths.py
uv run python tools/generate_plugin_views.py --check
uv run python tools/render_capability_inventory.py --check
uv run python tools/render_plugin_capability_matrix.py --check
rg -n 'bootstrap\.sh|~/.claude/scripts|~/.claude/config|configs/claude|manifest parallel-agent|manifest smoke' \
  --glob '!docs/legacy/**' --glob '!docs/PLUGIN_CAPABILITY_INVENTORY.md' \
  --glob '!docs/MIGRATION_RECOVERY.md' --glob '!docs/superpowers/specs/**' \
  --glob '!docs/superpowers/plans/**' \
  --glob '!src/manifest_agent/data/legacy_inventory.yml' \
  --glob '!tests/fixtures/legacy_homes/**' --glob '!tests/python/manifest_agent/test_migration.py'
uv run pytest tests/python -v
bats tests/bats/*.bats
pre-commit run --all-files
uv build
```

Expected: the `rg` command returns no matches outside the explicit migration/history evidence allowlist; all tests and hooks pass; the plugin release archive contains no bootstrap, shared-home, or symlink-hub files. The coordinator wheel contains only the declarative legacy inventory needed by `migrate`, not executable bootstrap code.

- [ ] **Step 10: Verify published-artifact behavior in a clean environment**

After a release candidate is uploaded, create a clean user account or disposable VM containing only `uv` and one harness, then run the documented `uvx` install, disconnect the network, exercise representative local skills, reconnect, reconcile, and uninstall. Repeat through the protected workflow for all six harnesses before marking `0.2.0` final.

- [ ] **Step 11: Commit**

```bash
git add -A bootstrap.sh bootstrap configs .apm templates tests/bats .github/workflows README.md AGENTS.md CLAUDE.md docs .gitignore .pre-commit-config.yaml pyproject.toml tools/build_manifest_release.py
git commit -m "feat!: retire bootstrap deployment for native plugins"
```

---

## Final Verification Checklist

- [ ] Every approved design section maps to at least one task and executable test.
- [ ] The canonical parity inventory contains exactly nine domain bundles and excludes `adversarial-design-loop`.
- [ ] All six adapters install at user scope, inspect effective capability state, preserve unowned settings, and uninstall from receipts.
- [ ] All bundle runtimes work with the repository, bootstrap, `uvx`, coordinator source, and other plugins absent.
- [ ] Required/default/optional capability semantics are tested, with Context7 default and authenticated MCP integrations opt-in.
- [ ] Migration proves one writer before and after handoff and restores legacy state on native verification failure.
- [ ] Concurrent mutations, partial convergence, atomic writes, rollback, repair, and recovery are covered.
- [ ] Generated native views, inventory, capability matrix, release index, and checksums are drift-checked.
- [ ] No skipped, absent, or unverifiable harness probe can produce a green parity verdict.
- [ ] The protected live matrix is green for Claude, Codex, Gemini, Cursor, Antigravity, and Devin before bootstrap deletion.
- [ ] Final repository scans contain no executable dependency on bootstrap or a shared Claude home.
