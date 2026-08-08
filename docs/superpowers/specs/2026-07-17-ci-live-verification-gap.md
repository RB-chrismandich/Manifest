# CI Platform Abstraction — Live Verification Gap (Phase 3, Tasks 19–22)

> Documentation-level status of Phase 3's GitLab CI abstraction work
> (`ci_platform.sh` + the `ci-audit-triggers` / `ci-reproduce-failure` /
> `ci-diagnose-drift` GitLab paths + `ci-setup`'s templates), and the concrete
> steps to close the live-test gap. Companion to
> [2026-07-17-gitlab-forge-verb-verification.md](2026-07-17-gitlab-forge-verb-verification.md)
> (that doc covers `git_ops.sh` PR/MR-forge verbs; this one covers the
> separate CI-platform-detection and CI-workflow-analysis skills — different
> scripts, different abstraction layer, kept as its own file rather than a
> section grafted onto that doc, since the two verification efforts don't
> share a matrix shape: forge verbs are single API calls, CI skills are
> multi-step audit/reproduction methods). Plan:
> `docs/superpowers/plans/2026-07-16-agent-app-agnostic-skills.md`, Task 22.

## Scope note (deviation from the original plan text)

Task 22's plan text calls for live-testing `ci-audit-triggers` and
`ci-reproduce-failure` against **a real GitLab project with a failing/
vulnerable pipeline**. That is not possible in this environment: `command -v
glab` fails (binary not installed) and no GitLab project or credentials are
available — the same gap hit and honestly documented in Task 12 (forge-op
matrix) and Task 16 (`git_ops.sh` forge-verb doc above). Per that precedent
(verify what's genuinely reachable, document what isn't, never fabricate a
live pass), this task was rescoped to:

1. The `ci-setup` gap pass itself (detection-logic check, GitLab template
   syntax check) — fully doable with no live access, done below.
2. This gap doc, recording what's doc/research-level verified vs.
   genuinely live-tested across Tasks 19–22, and the exact steps to close it
   once real `glab` + a GitLab project are available.

The plan's own Task 22 Step 1 text says to verify `ci-setup`'s detection
"now uses `ci_platform.sh`" — that instruction is corrected here: `ci_platform.sh`
(Task 19) detects whether CI config **already exists** in a repo (file
presence: `.github/workflows/*` vs `.gitlab-ci.yml`) — the right tool for
skills that analyze/reproduce *existing* CI. `ci-setup`'s job is different: it
runs on repos that may have **no** CI yet and must choose which template to
*write*, which is a "what platform does this repo's Git remote point at"
question — `git_platform.sh`'s job (remote-URL based), not `ci_platform.sh`'s.
Using `ci_platform.sh` for `ci-setup` would misdetect on the common case of a
GitLab-hosted repo that has no CI config yet (`ci_platform.sh` would return
`none`, not `gitlab-ci`). See "`ci-setup` detection logic" below for what was
actually found in the skill file.

## Status matrix — Tasks 19–22

| Task | Artifact | Verification level | Evidence basis |
|---|---|---|---|
| 19 | `configs/claude/scripts/ci_platform.sh` | **Unit-tested** | `tests/bats/ci_platform.bats` (5 cases: github-only, gitlab-only, both+github remote, both+gitlab remote, neither) — landed in `390d9e4`, run as part of this pass, PASS |
| 20 | `ci-audit-triggers` GitLab reference (`references/gitlab-ci-triggers.md`) | **Documentation-level only** | Written against GitLab's public docs (per Task 20's own commit `8851074`); never run against a real vulnerable GitLab pipeline |
| 21 | `ci-reproduce-failure` / `reproduce-gated-ci-failure-locally` / `ci-diagnose-drift` GitLab paths | **Documentation-level only** | Written against `glab ci`/`glab api` command shapes (Task 21 commit `d3b7ab2`); never run against a real failing GitLab pipeline |
| 22 | `ci-setup` detection logic | **Code-reviewed, confirmed correct as-is** | Read `.retired skill supply/skills/ci-setup/SKILL.md` directly — see findings below |
| 22 | `ci-setup` GitLab template (`templates/ci/gitlab/.gitlab-ci.yml`) | **Doc-level syntax-verified** | Checked against GitLab's current CI/CD YAML reference via live WebFetch — see findings below |
| 22 | `ci-audit-triggers` / `ci-reproduce-failure` live run against a real GitLab project | **NOT DONE — genuinely un-live-tested** | `glab` not installed, no GitLab project/credentials available in this environment |

No `verified: true` (or equivalent) flag is set anywhere in config as a
result of this pass — this repo has no CI-skill-specific verified-flag
config to begin with (`tracker_providers.yml` is Task 12's unrelated
issue-tracker registry).

## `ci-setup` detection logic — finding

Read `.retired skill supply/skills/ci-setup/SKILL.md` Step 1 in full. It already does
the correct thing and needed **no change**:

```bash
# Use git_platform.sh if available, otherwise check remote URL
platform=$(~/.claude/scripts/git_platform.sh 2>/dev/null || echo "github")
```

This is a direct call to `configs/claude/scripts/git_platform.sh` (deployed
path `~/.claude/scripts/git_platform.sh`, the same reference convention every
other CI skill uses for its own script) — not an inlined reimplementation of
remote-URL parsing, and not a call to `ci_platform.sh`. `git_platform.sh`
detects the hosting platform from `git remote get-url` (github.com →
`github`, gitlab.com/gitlab.\* → `gitlab`, else → `git`), which is exactly
the "which template should I write" question `ci-setup` needs answered — it
does not depend on any CI config already existing. No duplicate detection
logic was found to remove, and no edit was made to `ci-setup/SKILL.md`.

## `ci-setup` GitLab template — syntax findings

Read `templates/ci/gitlab/.gitlab-ci.yml` (288 lines: Python/Go/Node/
Terraform jobs + secret-scan + a `ci-gate` aggregator, all built on
`rules:`/`extends:`/`changes:`). Checked every keyword actually used against
GitLab's current public CI/CD YAML reference, fetched live in this session
(not recalled from training data):

| Keyword/pattern used in the template | Doc-level verdict | Evidence |
|---|---|---|
| `stages:` (detect/lint/test/security/gate) | Current | `docs.gitlab.com/ci/yaml/` |
| `rules:` + `rules:if` (all conditional jobs, incl. `secret-scan`/`ci-gate`) | Current | `docs.gitlab.com/ci/yaml/` |
| `rules:changes` (`.python_changes`/`.go_changes`/`.node_changes`/`.terraform_changes` templates) | Current | `docs.gitlab.com/ci/yaml/` |
| `extends:` (every job inherits its `_changes` template) | Current | `docs.gitlab.com/ci/yaml/` |
| `needs:` with `- job: X` / `optional: true` (`ci-gate`'s 9 optional deps) | Current | `docs.gitlab.com/ci/yaml/` |
| `artifacts:reports:coverage_report:coverage_format: cobertura` (python/go/node `:test` jobs) | Current | `docs.gitlab.com/ci/yaml/artifacts_reports/` — confirmed `cobertura` is a valid `coverage_format` value and the nested-key shape matches exactly |
| `image: name: … / entrypoint: [""]` (terraform/trivy jobs) | Current | Standard documented pattern for images with a non-shell entrypoint |
| `cache: key: / paths:` | Current | Standard, unchanged |
| **`only:` / `except:`** | **Not present anywhere in the file** | Confirmed via `grep -n "only:\|except:"` — zero matches. These two keywords are officially deprecated (`docs.gitlab.com/ci/yaml/deprecated_keywords/`) in favor of `rules:`, and the template already uses `rules:` exclusively, so there was nothing to fix |

**No changes were made to the template** — every keyword it uses is current,
non-deprecated GitLab CI syntax, cross-checked against a live fetch of
GitLab's own docs rather than assumed. `python3 -c "import yaml;
yaml.safe_load(...)"` also confirms the file parses as valid YAML (ordinary
syntax check, not a semantic/`glab ci lint` check — see gap below).

## What remains genuinely unverified (live-test instructions)

Nothing above touched a real GitLab instance. The following can only be
closed by someone with `glab` installed and authenticated against a real
GitLab project:

### Setup

```bash
brew install glab   # or: go install gitlab.com/gitlab-org/cli/cmd/glab@latest
glab auth login      # against a real GitLab.com project or self-managed instance
```

### 1. `ci-setup`'s generated `.gitlab-ci.yml` actually lints/runs

```bash
cd <scratch-gitlab-repo-checkout-with-python-and-node-files>
# Run ci-setup (or manually copy templates/ci/gitlab/.gitlab-ci.yml to the repo root)
glab ci lint .gitlab-ci.yml
```

Confirm `glab ci lint` reports the file syntactically and semantically valid
(catches things a plain YAML parse cannot: unknown keywords, bad `extends:`
targets, invalid `rules:` shapes). Then push a commit that touches a Python
file and confirm the `detect`→`lint`→`test`→`security`→`gate` stage sequence
actually fires the expected jobs (`python:lint`, `python:test`,
`python:security`) and skips the Go/Node/Terraform jobs via `rules:changes`.

### 2. `ci-audit-triggers` against a real vulnerable GitLab pipeline

Set up a scratch GitLab project with a deliberately vulnerable pipeline
(e.g. a job triggered by pipelines-for-merge-requests-from-forks that
interpolates `$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` or similar untrusted
input directly into a `script:` shell command, mirroring the GitHub
`pull_request_target` + fork `head.ref` pwn-request pattern the skill
already handles on the GitHub side). Run `ci-audit-triggers` against it,
confirm `ci_platform.sh` correctly reports `gitlab-ci`, confirm the skill
loads `references/gitlab-ci-triggers.md` and correctly (a) identifies the
injection, (b) correctly states GitLab's structural trust model (fork MR
pipelines run in the fork's own context by default, no parent secrets,
requires a manual "Run pipeline" click by a Developer+ parent-project member
to touch protected variables) rather than assuming a GitHub-style
runtime-`if:`-gate model.

### 3. `ci-reproduce-failure` against a real failing GitLab pipeline

Push a commit that deliberately fails a job (e.g. a syntax error picked up
by `python:lint`). Run `ci-reproduce-failure`, confirm `ci_platform.sh`
reports `gitlab-ci`, confirm the skill loads `references/gitlab-ci-reproduction.md`
and correctly uses `glab ci list --status failed` / `glab ci get --pipeline-id`
/ `glab ci trace <job-id>` to pinpoint the failing job (GitLab's
job-level granularity, not GitHub's step-level), reads `.gitlab-ci.yml`
(+ resolves any `include:`) to find the failing job's `script:` block, and
reproduces those commands locally against the pinned commit SHA.

### 4. Record results

Flip the corresponding rows in the status matrix above from "Documentation-
level only" / "NOT DONE" to "LIVE-VERIFIED" with a dated evidence section
(command output or a summarized transcript, not a bare boolean) — following
the same evidence-with-commands style used in
[2026-07-17-gitlab-forge-verb-verification.md](2026-07-17-gitlab-forge-verb-verification.md).
No `verified: true` config flag exists for these CI skills to flip; if one is
introduced later it must only be set after this transcript evidence exists.
