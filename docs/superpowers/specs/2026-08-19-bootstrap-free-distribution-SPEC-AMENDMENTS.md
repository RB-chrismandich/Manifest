# Bootstrap-Free Distribution Spec Amendments

Gaps found while reviewing `2026-08-01-bootstrap-free-plugin-distribution-design.md`
against the shipped `src/manifest_agent` coordinator on 2026-08-19.

Review method: single reviewer, direct measurement against the repository at
commit `ad1faee3`. Four delegated adversarial reviewers were dispatched and all
four terminated on context exhaustion, so these findings have **not** had
independent cross-verification. Every claim below cites what was measured.

## 1. There is no update operation at any layer

**What the spec says:** Section 7 defines the command surface as `install`,
`migrate`, `reconcile`, `reconcile --apply` and `uninstall`. Section 11 requires
that "native package managers own plugin download, update, caching, and
removal."

**The gap:** No adapter implements an update operation. A search for update or
upgrade verbs across all six adapters in `src/manifest_agent/adapters/` returns
nothing. There is no `update` command, and section 7 never defines one, so the
completion criterion in section 11 cannot be met by the current architecture.

Native per-harness auto-update cannot close this either, and the design is
already self-consistent in refusing it. Every adapter installs from a locally
materialized path (`desired.bundle_path(contract.name)` in the claude, codex,
gemini, cursor, antigravity and devin adapters), so no harness has a remote to
poll. `adapters/gemini.py:120` states the position explicitly: "Install each
verified bundle without enabling native auto-update", despite the Gemini CLI
supporting `gemini extensions install <source> --auto-update`. Enabling it would
contradict section 6: "Release resolution must use an immutable version or
commit plus published checksums; mutable branch heads are not an installation
identity." Six harnesses polling independently produce exactly the mixed bundle
generations section 6 defines as drift.

**Recommended spec change:** Add a normative `manifest update` verb to section 7
that re-resolves one pinned release and re-converges every installed harness in
a single transaction, reusing the section 8 lock, receipt and partial-
convergence semantics. State in section 6 that native per-harness auto-update
flags are forbidden, with the release-identity rule as the reason, so the
current adapter behavior is documented policy rather than an apparent omission.
Add the update path to the section 10 verification list and to the section 11
completion criteria, replacing the claim that native managers own update.

**Source:** Adapter search across `src/manifest_agent/adapters/`;
`adapters/gemini.py:120`; design sections 6, 7 and 11.

## 2. Bundle coverage was opt-in, so an unregistered bundle reported clean

**What the spec says:** Section 10 requires "a repository gate forbidding
bootstrap and legacy home-path runtime references", and that "skipped or
unverifiable checks must not produce a green parity verdict".

**The gap:** The gate exists as `tools/check_plugin_runtime_paths.py` and is
wired into CI, but it enumerated a hardcoded `DOMAIN_BUNDLES` tuple. Any
directory under `plugins/` absent from that tuple was scanned by nothing and
contributed no violations, so the gate returned `{"violations": []}` while
`plugins/manifest-delegate` contained seven legacy shared-home references,
including two executable ones: `HOME_CONFIG_DIR = os.path.expanduser(
"~/.claude/config")` at `manifest_delegate/constants.py:63`, and a resolved
`~/.claude/scripts/manifest_model_policy` path at `scripts/delegate.py:79`.

**Resolution already adopted:** Coverage is now opt-out. `_ungoverned_bundles()`
in `tools/check_plugin_runtime_paths.py` fails on any `plugins/` directory
present in neither `DOMAIN_BUNDLES` nor `ADDON_BUNDLES`, unless it is recorded
in a new `UNGOVERNED_BUNDLES` map with a stated reason. Two tests cover the
guard, both mutation-verified.

**Recommended spec change:** State in section 10 that bundle coverage is
opt-out, and that adding a bundle without a portable contract is itself a gate
failure rather than a silent exclusion.

**Source:** `tools/check_plugin_runtime_paths.py`;
`src/manifest_agent/contracts.py:20-31`; `tests/python/test_plugin_runtime_paths.py`.

## 3. manifest-delegate ships outside the portable-contract system

**What the spec says:** Section 2.2 names the canonical capability sources and
section 2.3 requires that each bundle contain one portable capability contract
from which native views are generated. Section 2.4 installs all bundles into
every detected harness.

**The gap:** `plugins/manifest-delegate` is published in
`.claude-plugin/marketplace.json` and installs under Claude Code, but it has no
`manifest-capabilities.yml`, no `gemini-extension.json` and no
`antigravity-extension.json`, and it appears in neither `DOMAIN_BUNDLES` nor
`ADDON_BUNDLES`. No harness adapter enumerates it. The practical consequence is
that delegation, the multi-agent capability delivered by feature 675, is
Claude-only and cannot be installed into Codex, Gemini, Cursor, Antigravity or
Devin by the coordinator. This is the probable root cause of open issue #784,
"Add support for Delegation setup to include Cursor and Devin", which reads as a
feature request but is a packaging gap.

**Recommended spec change:** Either give the bundle a portable contract and add
it to `ADDON_BUNDLES`, or record in section 2.2 that it is deliberately
Claude-only and outside the parity contract. Until one is chosen, the exclusion
is declared in `UNGOVERNED_BUNDLES` so it is visible rather than invisible.

**Source:** `plugins/manifest-delegate/` contents;
`src/manifest_agent/contracts.py:20-31`; issue #784.

## 4. Hook re-homing is gated on licensed live evidence

**What the spec says:** Stage 2 requires bundles to be self-contained with no
runtime dependency on legacy home paths. Stage 3 requires all six adapters
tested against isolated homes and states that "no harness is accepted as a
permanent exception to the parity contract."

**The gap:** Seven hooks are still registered by bootstrap into
`~/.claude/settings.json` with `~/.claude/scripts/` commands:
`block_cwd_delete.py`, `constitution_hook.py`, `deploy_stamp_check.sh`,
`guidance_hint.py`, `lint_on_edit_hook.sh`, `subagent_model_default.py`, and
`spec_review.sh --silent`. Only `version_pin_hook.sh` has completed the trip to
a bundle, script and hook registration together. `spec_review.sh` is
half-migrated: its script ships as a declared runtime component of
`manifest-spec-planning`, but that contract declares `hooks: []`, so nothing
registers it. Two of the unmigrated hooks are safety controls
(`block_cwd_delete.py`, `subagent_model_default.py`) and would fail silently.

Completing a re-homing is not a desk change. Registering the `spec-review` hook
was attempted and correctly rejected by
`tools/render_plugin_capability_matrix.py --check`, which emitted
`BLOCKED(components evidence missing manifest-spec-planning:hook:spec-review)`
for the two harnesses claiming a working mode. Capability evidence comes from
`.github/workflows/plugin-parity-live.yml`, which requires licensed harness
secrets. Stage 3's no-exceptions rule therefore collides with an evidence
supply that is gated on credentials, and the sequencing is unstated.

**Recommended spec change:** Add to Stage 3 that each hook migration requires a
live parity run to supply capability evidence before its contract change can
merge, and name who can trigger it. Record in Stage 6 that
`deploy_stamp_check.sh` is **retired rather than re-homed**: it validates the
bootstrap deploy stamp and has no meaning once bootstrap is gone.

**Source:** `configs/claude/settings.runtime.json`;
`bootstrap/lib/deploy.sh` `merge_settings_hooks`;
`plugins/manifest-spec-planning/manifest-capabilities.yml`;
`tools/render_plugin_capability_matrix.py:264-270`.

## 5. Stage status is unrecorded and untracked

**The gap:** Work began 2026-08-01 and the most recent coordinator commit is the
same day as this review, so the migration is active rather than stalled. No open
issue tracks bootstrap retirement, the update verb, or hook re-homing, and the
six stages carry no recorded status. Measured against the tree: Stage 1 and
Stage 5 appear done, Stage 2 and Stage 3 are partial, and Stage 6 has not
started (`bootstrap.sh` is 6,330 lines and remains the documented install path).
Test isolation is a specific Stage 3 weakness: 8 of 65 coordinator test files
isolate HOME, so most of the suite can pass on ambient state that Stage 6
removes.

**Recommended spec change:** Add a status column to the section 9 stage list,
kept current, and open one tracking issue per remaining stage.

**Source:** `git log src/manifest_agent/`; `gh issue list`; HOME-isolation search
across `tests/python/manifest_agent/`.
