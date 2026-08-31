# Manifest i-have-adhd Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Ship a pinned, attributed, always-on manifest-i-have-adhd plugin across every supported harness and reversibly
replace the incompatible upstream Codex installation.

**Architecture:** Mirror only the reviewed upstream skill, license, and behavior into a self-contained Manifest bundle
with an immutable provenance lock. Deliver always-on behavior through native session hooks where available and generated
always-loaded guidance elsewhere; route hook failures to bounded Manifest diagnostics. Add receipt-backed Codex
configuration mutation so the upstream plugin is disabled only after the mirrored replacement verifies.

**Tech Stack:** Markdown skills, YAML portable contracts, generated JSON plugin views, Python 3.11 hook launcher,
tomllib, SHA-256 provenance, pytest, Bats.

**Prerequisite:** Complete Tasks 1 through 5 of `2026-08-09-codex-bootstrap-plugin-reconciliation.md` first so the new
bundle participates in catalog synchronization and receipt-backed cutover.

## Global Constraints

- Bundle name: `manifest-i-have-adhd`; skill name: `i-have-adhd`.
- Upstream source: [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd), pinned to one exact commit and MIT
  license.
- Bootstrap and runtime never fetch mutable upstream content.
- The bundle is always-on for every supported harness; missing delivery is BLOCKED, not silently degraded.
- Hook execution is advisory and exits zero after recording a bounded diagnostic.
- `i-have-adhd@i-have-adhd` is disabled only after `manifest-i-have-adhd@manifest` and its hook probe verify.
- The upstream plugin is never uninstalled automatically.
- Rollback restores only enabled state that a Manifest receipt proves it changed.

---

## File Structure

- Create plugins/manifest-i-have-adhd/: mirrored bundle, contract, views, hook, guidance, license, and provenance lock.
- Create tools/sync_i_have_adhd.py: reviewed upstream synchronization and checksum verification.
- Create src/manifest_agent/codex_config.py: narrow atomic editor for plugin enabled state in Codex TOML.
- Modify src/manifest_agent/adapters/codex.py: conflict detection, hook probe, disable, and rollback ownership.
- Modify tools/generate_plugin_views.py: emit always-on delivery for all harnesses.
- Modify .claude-plugin/marketplace.json: publish the local mirrored bundle.
- Test in tests/python/test_sync_i_have_adhd.py, tests/python/plugin_runtime/test_adhd_runtime.py,
  tests/python/manifest_agent/test_codex_config.py, adapter tests, and generated-view tests.

### Task 1: Add Pinned Upstream Provenance

**Files:**

- Create: tools/sync_i_have_adhd.py
- Create: plugins/manifest-i-have-adhd/upstream-lock.json
- Create: plugins/manifest-i-have-adhd/LICENSE.upstream
- Test: tests/python/test_sync_i_have_adhd.py

**Interfaces:**

- Produces: load_upstream_lock(path: Path) -> UpstreamLock.
- Produces CLI: python tools/sync_i_have_adhd.py --source PATH --commit SHA [--apply].
- Lock fields: repository, commit, license, files, synced_at.

- [ ] **Step 1: Write failing provenance tests**

Add `write_locked_bundle()`, `write_upstream_fixture()`, and `snapshot_tree()` as focused test helpers in the same test
module; they create only files under the pytest temporary directory.

```python
def test_lock_pins_full_commit(repo_root):
    lock = load_upstream_lock(
        repo_root / "plugins/manifest-i-have-adhd/upstream-lock.json"
    )
    assert re.fullmatch(r"[0-9a-f]{40}", lock.commit)
    assert lock.repository == "https://github.com/ayghri/i-have-adhd"
    assert lock.license == "MIT"


def test_verify_rejects_changed_mirrored_file(tmp_path):
    bundle, lock = write_locked_bundle(tmp_path, content="original")
    (bundle / "skills/i-have-adhd/SKILL.md").write_text("changed")
    with pytest.raises(SyncError, match="checksum mismatch"):
        verify_mirror(bundle, lock)


def test_dry_run_writes_nothing(tmp_path):
    source, bundle = write_upstream_fixture(tmp_path)
    before = snapshot_tree(bundle)
    result = sync_upstream(source, bundle, apply=False)
    assert result.changed is True
    assert snapshot_tree(bundle) == before
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: uv run pytest tests/python/test_sync_i_have_adhd.py -q

Expected: FAIL because the sync tool and lock do not exist.

- [ ] **Step 3: Implement the explicit sync tool**

The tool accepts an already checked-out upstream directory and verifies:

```python
if _git(source, "rev-parse", "HEAD") != commit:
    raise SyncError("upstream checkout does not match --commit")
```

Copy only skills/i-have-adhd/SKILL.md and LICENSE. Do not copy .git, workflows, package manifests, logos, translations,
or upstream marketplace files. The --apply mode writes normalized mirrored files and a sorted checksum map; dry-run
prints the proposed lock.

- [ ] **Step 4: Record the reviewed upstream revision**

Run git -C ~/.codex/plugins/cache/i-have-adhd/i-have-adhd/0.1.0 rev-parse HEAD to discover the full commit, then run the
sync tool from a clean checkout at that commit. Review attribution and the complete diff before accepting it.

- [ ] **Step 5: Run provenance tests**

Run: uv run pytest tests/python/test_sync_i_have_adhd.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/sync_i_have_adhd.py tests/python/test_sync_i_have_adhd.py \
  plugins/manifest-i-have-adhd/upstream-lock.json \
  plugins/manifest-i-have-adhd/LICENSE.upstream
git commit -m "chore(adhd): pin mirrored upstream provenance"
```

### Task 2: Build the Harness-Neutral Always-On Runtime

**Files:**

- Create: plugins/manifest-i-have-adhd/skills/i-have-adhd/SKILL.md
- Create: plugins/manifest-i-have-adhd/hooks/always_on.py
- Create: plugins/manifest-i-have-adhd/hooks/hooks.json
- Create: plugins/manifest-i-have-adhd/guidance/always-on.md
- Test: tests/python/plugin_runtime/test_adhd_runtime.py

**Interfaces:**

- Produces: render_instructions(skill_path: Path) -> str.
- Produces: record_hook_failure(state_root: Path, diagnostic: HookDiagnostic) -> None.
- CLI contract: read session JSON from stdin, write instructions to stdout, always exit zero.

- [ ] **Step 1: Write runtime tests**

Cover frontmatter stripping, script-relative skill resolution, independence from CLAUDE_PLUGIN_ROOT, fail-open behavior,
SHA-256 diagnostic deduplication, mode 0600, and the newest-100-record bound.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: uv run pytest tests/python/plugin_runtime/test_adhd_runtime.py -q

Expected: FAIL because the runtime does not exist.

- [ ] **Step 3: Add the mirrored skill**

Preserve the reviewed upstream rules, MIT attribution, trigger phrases, stop phrases, and safety exceptions. Remove
unsupported upstream-only frontmatter keys. Keep the description on one compact line.

- [ ] **Step 4: Implement the fail-open launcher**

```python
def main() -> int:
    try:
        payload = json.load(sys.stdin)
        instructions = render_instructions(_skill_path())
        sys.stdout.write(_activation_banner(payload) + "\n\n" + instructions + "\n")
    except Exception as error:
        record_hook_failure(_state_root(), HookDiagnostic.from_error(error))
    return 0
```

Fingerprint plugin, harness, version, error class, and message. Write diagnostics atomically and retain the newest 100
distinct records.

- [ ] **Step 5: Add hook and guidance assets**

hooks/hooks.json declares SessionStart for native hook harnesses. guidance/always-on.md contains equivalent instructions
for adapters that install always-loaded guidance.

- [ ] **Step 6: Run runtime tests**

Run: uv run pytest tests/python/plugin_runtime/test_adhd_runtime.py -q

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add plugins/manifest-i-have-adhd/skills \
  plugins/manifest-i-have-adhd/hooks \
  plugins/manifest-i-have-adhd/guidance \
  tests/python/plugin_runtime/test_adhd_runtime.py
git commit -m "feat(adhd): add harness-neutral always-on runtime"
```

### Task 3: Add the Portable Contract and Generated Views

**Files:**

- Create: plugins/manifest-i-have-adhd/manifest-capabilities.yml
- Create: generated plugin views under plugins/manifest-i-have-adhd/
- Modify: .claude-plugin/marketplace.json
- Modify: tools/generate_plugin_views.py
- Modify: schemas/manifest-capabilities.schema.json
- Test: tests/python/manifest_agent/test_generate_plugin_views.py
- Test: tests/python/manifest_agent/test_contracts.py

**Interfaces:**

- Adds marketplace ID manifest-i-have-adhd@manifest.
- Declares one skill, one hook, one guidance component, and required python3.
- Requires effective always-on delivery for claude, codex, gemini, cursor, antigravity, and devin.

- [ ] **Step 1: Add failing contract and generation tests**

Assert the bundle appears in the marketplace, every harness has an effective always-on component, and no generated
command contains CLAUDE_PLUGIN_ROOT.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: uv run pytest tests/python/manifest_agent/test_contracts.py
tests/python/manifest_agent/test_generate_plugin_views.py -q

Expected: FAIL because the contract and generation rules do not exist.

- [ ] **Step 3: Write the portable contract**

```yaml
components:
  skills:
    root: skills
    include: ["*/SKILL.md"]
  hooks:
    - id: adhd-session-start
      path: hooks/hooks.json
      compatibility:
        claude: { mode: native }
        codex: { mode: native }
        gemini: { mode: generated }
        cursor: { mode: generated }
        antigravity: { mode: imported }
        devin: { mode: generated }
  guidance:
    - id: adhd-always-on-guidance
      path: guidance/always-on.md
```

Declare python3 required and record both Manifest and upstream provenance.

- [ ] **Step 4: Generate harness-native delivery**

Claude and Codex reference the relative Python hook. Gemini and Devin receive always-loaded native context. Cursor
receives an alwaysApply rule. Antigravity imports the guidance. Generation fails closed when neither hook nor
always-loaded guidance can represent the bundle.

- [ ] **Step 5: Regenerate and verify views**

```bash
PYTHONPATH=src uv run python tools/generate_plugin_views.py --repo-root .
PYTHONPATH=src uv run python tools/generate_plugin_views.py --check --repo-root .
```

Expected: generated views are stable and the check exits zero.

- [ ] **Step 6: Commit**

```bash
git add plugins/manifest-i-have-adhd .claude-plugin/marketplace.json \
  tools/generate_plugin_views.py schemas/manifest-capabilities.schema.json \
  tests/python/manifest_agent/test_contracts.py \
  tests/python/manifest_agent/test_generate_plugin_views.py
git commit -m "feat(adhd): publish cross-harness plugin views"
```

### Task 4: Add Safe Codex Enabled-State Editing

**Files:**

- Create: src/manifest_agent/codex_config.py
- Modify: src/manifest_agent/models.py
- Modify: src/manifest_agent/state.py
- Test: tests/python/manifest_agent/test_codex_config.py

**Interfaces:**

- Produces: PluginEnabledChange(plugin_id: str, previous: bool | None, current: bool).
- Produces: set_plugin_enabled(path: Path, plugin_id: str, enabled: bool) -> PluginEnabledChange.
- Produces receipt ownership kind plugin-enabled-state.

- [ ] **Step 1: Write TOML preservation tests**

Cover existing true/false, absent tables, comments, quoted IDs, duplicate keys, malformed TOML, symlink paths, atomic
failure, and byte-identical no-op behavior.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/manifest_agent/test_codex_config.py -q

Expected: FAIL because codex_config.py does not exist.

- [ ] **Step 3: Implement a narrow validated editor**

Parse the full file with tomllib. Locate only:

```toml
[plugins."i-have-adhd@i-have-adhd"]
enabled = true
```

Replace or insert only enabled. Reparse the candidate, prove unrelated parsed values are unchanged, write mode 0600 to a
sibling temporary file, fsync, and replace atomically. Reject duplicate matching tables and symlinked config files.

- [ ] **Step 4: Add receipt validation**

Store plugin ID, prior boolean or absence, and exact config path in an OwnedEntry. Reject other target paths and plugin
IDs when decoding receipts.

- [ ] **Step 5: Run tests**

Run: uv run pytest tests/python/manifest_agent/test_codex_config.py tests/python/manifest_agent/test_state.py -q

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manifest_agent/codex_config.py src/manifest_agent/models.py \
  src/manifest_agent/state.py tests/python/manifest_agent/test_codex_config.py \
  tests/python/manifest_agent/test_state.py
git commit -m "feat(codex): record reversible plugin enabled state"
```

### Task 5: Migrate the Existing Upstream Codex Plugin

**Files:**

- Modify: src/manifest_agent/adapters/codex.py
- Modify: src/manifest_agent/bootstrap_sync.py
- Test: tests/python/manifest_agent/test_adapter_codex.py
- Test: tests/python/manifest_agent/test_bootstrap_sync.py
- Test: tests/python/manifest_agent/test_service_uninstall.py

**Interfaces:**

- Consumes set_plugin_enabled() from Task 4.
- Produces CodexAdapter.probe_plugin_hook(plugin_id: str) -> HarnessResult.
- Records upstream enabled-state ownership only after mirrored hook readiness.

- [ ] **Step 1: Add failing migration-order tests**

Assert this exact order:

```text
install manifest-i-have-adhd
inspect mirrored plugin
probe mirrored SessionStart hook
disable i-have-adhd@i-have-adhd
final inspect
skill cutover
receipt write
```

At every failure boundary, assert the upstream plugin remains enabled unless the mirrored plugin and hook already
verified.

- [ ] **Step 2: Run tests and confirm they fail**

Run: uv run pytest tests/python/manifest_agent/test_adapter_codex.py tests/python/manifest_agent/test_bootstrap_sync.py
-q

Expected: FAIL because conflict migration is absent.

- [ ] **Step 3: Detect only the exact external conflict**

Match only i-have-adhd@i-have-adhd. Never disable similarly named plugins or plugins from another marketplace.

- [ ] **Step 4: Implement the hook probe**

Invoke the installed mirrored launcher with a minimal SessionStart payload and isolated diagnostic root. Require exit
zero and an activation banner containing the mirrored version. Empty output is verification failure.

- [ ] **Step 5: Disable and record upstream state**

```python
change = set_plugin_enabled(config_path, "i-have-adhd@i-have-adhd", False)
```

Attach ownership only when previous is true. Restore on final-inspection or receipt-write failure.

- [ ] **Step 6: Restore on uninstall**

Restore enabled = true only for the exact receipt-owned entry. Leave the upstream plugin installed.

- [ ] **Step 7: Run migration tests**

Run: uv run pytest tests/python/manifest_agent/test_adapter_codex.py tests/python/manifest_agent/test_bootstrap_sync.py
tests/python/manifest_agent/test_service_uninstall.py -q

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/manifest_agent/adapters/codex.py src/manifest_agent/bootstrap_sync.py \
  tests/python/manifest_agent/test_adapter_codex.py \
  tests/python/manifest_agent/test_bootstrap_sync.py \
  tests/python/manifest_agent/test_service_uninstall.py
git commit -m "feat(adhd): migrate incompatible Codex plugin safely"
```

### Task 6: Add Smoke Tests and Documentation

**Files:**

- Create: tests/python/manifest_agent/test_adhd_codex_native.py
- Modify: docs/CONFIGURATION.md
- Modify: docs/TROUBLESHOOTING.md
- Modify: docs/PLUGIN_CAPABILITY_MATRIX.md
- Modify: CHANGELOG.md

- [ ] **Step 1: Add an opt-in native test**

Start from an isolated Codex home with the upstream plugin enabled. Assert the mirrored plugin is installed, the
upstream plugin remains installed but disabled, the hook emits instructions without diagnostics, and a second sync is a
no-op.

- [ ] **Step 2: Document behavior and recovery**

Document stop adhd mode, always-on delivery, diagnostic location, why upstream remains installed, and how uninstall
restores its previous enabled state.

- [ ] **Step 3: Regenerate capability documentation**

Run: PYTHONPATH=src uv run python tools/render_plugin_capability_matrix.py

Expected: the new bundle is READY only where always-on delivery is present.

- [ ] **Step 4: Run focused verification**

```bash
uv run pytest tests/python/test_sync_i_have_adhd.py \
  tests/python/plugin_runtime/test_adhd_runtime.py \
  tests/python/manifest_agent/test_codex_config.py \
  tests/python/manifest_agent/test_adapter_codex.py \
  tests/python/manifest_agent/test_bootstrap_sync.py -q
PYTHONPATH=src uv run python tools/generate_plugin_views.py --check --repo-root .
```

Expected: all focused gates pass.

- [ ] **Step 5: Commit**

```bash
git add tests/python/manifest_agent/test_adhd_codex_native.py \
  docs/CONFIGURATION.md docs/TROUBLESHOOTING.md \
  docs/PLUGIN_CAPABILITY_MATRIX.md CHANGELOG.md
git commit -m "docs(adhd): document mirrored always-on plugin"
```
