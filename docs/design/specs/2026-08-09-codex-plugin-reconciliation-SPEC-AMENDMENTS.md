# Codex Plugin Reconciliation Spec Amendments

Gaps found while implementing and verifying
`2026-08-09-codex-plugin-reconciliation-design.md`.

## 1. Bound native startup visibility - Problem and Codex Skill Cutover

**What the spec says:** The original problem statement attributes the skills
context warning to overlapping native plugins and the retained flat
`~/.codex/skills` catalog. The chosen approach retires that flat catalog after
native verification.

**The gap (found implementation review 1, Codex runtime lens):** Live
`codex debug prompt-input` inspection after the legacy catalog had already been
removed still showed 120 model-visible skills and the context-budget warning.
The enabled native Manifest catalog alone was large enough to cross Codex's
2%/8,000-character startup metadata limit. Legacy retirement is necessary but
not sufficient.

**Resolution already adopted:** `tools/generate_plugin_views.py` emits
`agents/openai.yaml` for every repository skill. Three qualified routing and
discovery entry points allow implicit invocation; every other Manifest skill is
explicit-only but remains installed and callable. The allowlist is validated
against the repository catalog. Prepared local reconciliation also forces a
marketplace refresh when installed and desired plugin trees differ at the same
version, so existing caches receive the generated metadata.

**Recommended spec change:** State the native-catalog finding in the Problem
section, add a normative Codex Startup Skill Policy section, and require native
acceptance coverage to inspect `codex debug prompt-input` in addition to checking
session warnings.

**Source:** Live Codex prompt-input reproduction; generated-view regression
tests; native Codex acceptance test.

## Amendment Status Note

Amendment 1 is adopted and landed in the current worktree. Its implementation,
tests, normative spec edit, and rationale file must be committed atomically.
