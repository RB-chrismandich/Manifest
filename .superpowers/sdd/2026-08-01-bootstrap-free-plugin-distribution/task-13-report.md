# Task 13 Report: Self-Contained Code Quality and Docs Bundles

## Result

Implemented bundle-local, offline runtimes for `manifest-code-quality` and
`manifest-docs`. Constitution checks, smoke catalogs, project scaffolds, audit
references, and docs linting no longer depend on `configs/claude`, an assistant
home, the legacy `manifest` router, or runtime network access.

## TDD Evidence

- RED: focused pytest failed 9/9 on missing scripts, assets, contracts, and
  legacy runtime references; the new Bats suites failed 4/4 at the same seams.
- RED follow-up: malformed smoke stdin returned exit 1, unusable docs policies
  silently fell back, and immutable vendor paths were not excluded from
  formatting hooks.
- GREEN: focused pytest passes 17/17 under empty homes, `UV_NO_NETWORK=1`,
  empty `PYTHONPATH`, and `python -S -B`.
- GREEN: the combined plugin and migrated legacy Bats suites pass 40/40.

## Implementation

- Packaged the complete constitution checker beside
  `code-audit-constitution`, converted its immutable policy to adjacent JSON,
  retained its baseline and language annexes, and removed runtime PyYAML use.
- Packaged the complete smoke orchestrator and schemas beside `smoke-manage`.
  `scripts/smoke.py` prepends only the adjacent vendor directory and preserves
  exit codes 0/1/2, including exit 2 for malformed workflow JSON.
- Added deterministic PyYAML vendoring from the exact `uv.lock` 6.0.3 sdist.
  The tool verifies the official PyPI source, locked SHA-256, hard-allowlisted
  pure-Python package files, MIT license, and committed per-file hashes. It
  rejects native or unexpected package members and checks without network.
- Copied all four scaffold trees byte-for-byte beside `project-scaffold` and
  added a drift test against the temporary top-level compatibility source.
- Packaged the code-audit antipattern reference and changed all cross-domain
  collaboration to `[[skill:...]]` interfaces.
- Packaged docs lint, its concision doctrine, and an adjacent stdlib-readable
  JSON limits policy. Explicit overrides are JSON-only and fail closed with
  exit 2; the runtime never imports ambient YAML or silently changes policy.
- Declared every runtime directory and exact required/optional executable tier,
  then regenerated the Claude, Gemini, and generic native views.
- Migrated the named legacy Bats suites to execute plugin copies only.
- Added narrow immutable-vendor exclusions to byte-mutating and style hooks.
  Owned bundle runtime and `VENDOR.json` remain checked, while AST, debug,
  secret, and JSON hooks continue to inspect the upstream tree. The relocated
  smoke runtime retains the legacy constitution ratchet rather than bypassing
  the gate, and the exact Node scaffold is excluded only from root ESLint.

## Dependency Review

- Official PyPI reports non-yanked `PyYAML==6.0.3`, `Requires-Python >=3.8`,
  legacy license metadata `MIT`, and sdist SHA-256
  `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f`.
- The committed sdist digest matches both PyPI and `uv.lock`.
- The OSV query for PyPI `PyYAML` version 6.0.3 returned zero vulnerabilities.

## Verification

```text
uv run pytest tests/python/plugin_runtime/test_code_quality_runtime.py \
  tests/python/plugin_runtime/test_docs_runtime.py -q
# 17 passed

bats tests/bats/code_quality_plugin_runtime.bats \
  tests/bats/docs_plugin_runtime.bats tests/bats/constitution_check.bats \
  tests/bats/smoke_orchestrator_cli.bats tests/bats/docs_lint.bats
# 40 passed

uv run python tools/vendor_bundle_dependencies.py --check
# vendored PyYAML 6.0.3 is current

uv run python tools/generate_plugin_views.py --check
# passed

{ git diff-tree --no-commit-id --name-only -r HEAD; \
  printf '%s\n' .pre-commit-config.yaml \
    configs/claude/config/constitution_baseline.json; } \
  | sort -u | xargs pre-commit run --files
# passed without --no-verify
```

Scoped Ruff, Ruff format, Pyright, ShellCheck, yamllint, JSON/YAML validation,
secret checks, markdown lint, stale-path checks, and the Code Constitution
passed for authored and adapted Task 13 files. The no-baseline constitution
audit reported advisory findings only.

The full Task 13 changed-file pre-commit gate passes. Running it over every
vendor path leaves the tree unchanged, and the subsequent offline vendor check
confirms every `VENDOR.json` hash still matches the committed bytes.

## Scope Preservation

The known unrelated edits to `AGENTS.md`, `bootstrap/lib/deploy.sh`,
`docs/DEPLOY_OWNERSHIP.md`, and `tests/bats/deploy_skills.bats` remain unstaged
and unchanged by Task 13. No real assistant home, native plugin inventory, or
runtime network path was used.
