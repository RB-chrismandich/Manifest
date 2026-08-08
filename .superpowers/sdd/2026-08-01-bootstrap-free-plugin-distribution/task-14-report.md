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
- REPAIR RED: three focused tests and two Ops Bats cases reproduced duplicate
  shared-home hook registration, missing-target success, and malformed-policy
  traceback behavior.
- P1 RED: existing-home Claude and Gemini fixtures reproduced the additive-only
  bootstrap gap: removing the source registrations left already-deployed
  `version_pin_hook.sh` entries active indefinitely.
- GREEN: the focused suite now passes 33/33, including helper behavior parity,
  stdlib-only JSON policy loading, sibling-bundle absence, and complete
  generated hook/runtime views.
- P1 GREEN: both hook mergers now remove only the retired shared-home command;
  Claude also removes the two exact historical permission grants. Sibling and
  user-owned hooks/rules retain their order, and a second run is idempotent.
- GREEN: the expanded Task 14 Bats matrix passes 126/126.

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
- Retired the duplicate shared-home registrations and permissions from the
  Claude, Cursor, and Gemini config sources. Existing spec-review, lint,
  guidance, session, MCP, and user-owned hook entries remain unchanged.
- Added a bootstrap migration for existing Claude and Gemini homes. It prunes
  only the exact retired `~/.claude/scripts/version_pin_hook.sh` command, drops
  an emptied matcher wrapper, and retains every unrelated nested hook.
- Existing Claude homes also prune only the exact historical grants for
  `version_pin.sh` and `version_pin_hook.sh`; near-matches and all remaining
  permission rules preserve their original order.
- Missing explicit targets now return exit 2 before printing a summary.
  Malformed adjacent JSON policies return a concise exit-2 config diagnostic
  without a Python traceback.
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
# 33 passed

bats tests/bats/ops_plugin_runtime.bats \
  tests/bats/security_plugin_runtime.bats tests/bats/ci_platform.bats \
  tests/bats/version_pin.bats
# 38 passed

bats tests/bats/deploy_runtime_settings.bats tests/bats/spec_review.bats \
  tests/bats/cursor_hooks.bats tests/bats/gemini_hooks_merge.bats
# expanded runtime/config matrix: 126 passed total with the named suites

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
