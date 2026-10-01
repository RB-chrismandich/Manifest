---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Diagnoses that the test depends on ambient state — the developer's real global git config in HOME (`~/.gitconfig`) / repo config — which CI doesn't have.
2. The fix isolates ALL git config scopes: `GIT_CONFIG_GLOBAL` points at a fixture file, `GIT_CONFIG_NOSYSTEM=1` (or `GIT_CONFIG_SYSTEM` at an empty fixture) disables system config, and git runs with `cwd` outside any repository (e.g. a tmp dir; `GIT_CEILING_DIRECTORIES` or equivalent) so repo-local config can't leak — then asserts against the fixture's value. Redirecting only `HOME`/`XDG_CONFIG_HOME` FAILS; skipping the test in CI or loosening the assertion FAILS.
3. It also tests the absent-config case or notes what `git_author()` returns when no email is configured.
