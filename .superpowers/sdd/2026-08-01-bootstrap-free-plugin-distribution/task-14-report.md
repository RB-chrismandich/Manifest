# Task 14 Report: Self-Contained Ops and Security Bundles

## Result

Made `manifest-ops` and `manifest-security` independently installable. Each
bundle owns behavior-compatible CI and git platform helpers, resolves only its
own runtime assets, and operates under an empty home with the sibling bundle
absent.

## TDD Evidence

- RED: the new focused runtime suite collected 22 tests and failed 22 on the
  missing CI/git helpers, Ops version-pin runtime and hook contract, Security
  references, shared-home skill paths, and empty contract inventories.
- GREEN: the focused suite now passes 30/30, including helper behavior parity,
  stdlib-only JSON policy loading, sibling-bundle absence, and complete
  generated hook/runtime views.
- GREEN: the named plugin and legacy Bats suites pass 38/38.

## Ops Runtime

- Packaged independent `ci_platform.sh` and `git_platform.sh` copies governed
  by the existing CI-platform behavior contract.
- Packaged `version_pin.sh` with adjacent `version_pin.json`; runtime policy
  loading uses only Python's stdlib `json` module and retains the existing
  resolver, hashing, check-mode, bypass, and idempotency behavior.
- Added an ownership-marked advisory save hook and bundle-local fail-open
  adapter. Claude and Cursor receive native/generated hook states; Gemini,
  Codex, Antigravity, and Devin explicitly report degraded hook coverage while
  retaining the on-demand skill.
- Packaged the GitLab CI reproduction reference and rewired Ops skills to
  bundle-relative runtime paths. CI setup no longer searches assistant homes or
  emits a dependency on the shared Manifest coordinator.

## Security Runtime

- Packaged independent CI/git platform helpers and the GitLab trigger,
  antipattern, and security-relevant constitution references.
- Rewired CI and code-audit skills to bundle-local references and Task 11
  `[[skill:parallel-agent]]` / `[[skill:learning-capture]]` interfaces.
- Declared Semgrep optional: default inline auditing does not fail when it is
  absent; only a selected capability or explicitly requested Semgrep mode
  requires the executable.
- Removed shared config/sub-agent paths from Security skills and declared only
  the Security-owned runtime tree in its contract.

## Verification

```text
uv run pytest tests/python/plugin_runtime/test_ops_runtime.py \
  tests/python/plugin_runtime/test_security_runtime.py -q
# 30 passed

bats tests/bats/ops_plugin_runtime.bats \
  tests/bats/security_plugin_runtime.bats tests/bats/ci_platform.bats \
  tests/bats/version_pin.bats
# 38 passed

uv run python tools/generate_plugin_views.py --check
# passed

manifest smoke run --tier Lite
# 7 passed; verdict PASS
```

Scoped Ruff, Ruff format, ShellCheck, JSON validation, Bash syntax, generated
view checks, and changed-file pre-commit hooks pass. The repository-wide Ruff
scan reports the previously committed vendored PyYAML source; Task 14 files are
clean. Repository-wide pytest collection remains unavailable because the
existing environment lacks `rich`, while the focused Python and Bats suites run
without network or home dependencies.

## Scope Preservation

The pre-existing unrelated edits to `AGENTS.md`, `bootstrap/lib/deploy.sh`,
`docs/DEPLOY_OWNERSHIP.md`, and `tests/bats/deploy_skills.bats` remain unstaged
and unchanged. No real assistant home or sibling plugin runtime was used.
