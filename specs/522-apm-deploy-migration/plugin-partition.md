# Skill→Plugin Partition and Shared-Script Graph

**Produced by**: T036 + T037 (US4, FR-025/FR-026) · **Measured**: 2026-07-27
**Status**: analysis only — no plugin is packaged, no script is moved.

US4 (plugin packaging) is explicitly optional and deferrable. This document
settles the two questions that must be answered *before* anyone runs `apm pack`,
so the decision is not made implicitly by whoever does.

## T036 — the skill→domain map, derived functionally

108 skills. T036 requires the map be derived by **functional analysis, not
name-prefix matching**, and that the result be asserted as a true partition.

Name-prefixing fails on this corpus, concretely:

- `pr-review` and `repo-clean` both work on pull requests, but `repo-clean` also
  prunes branches — a `pr-*` prefix rule puts them in different plugins and
  splits one workflow.
- `spec-audit-tasks`, `speckit-*` and `lifecycle-run` share no prefix and are
  the same domain.
- `shell-refactor` consumes `git_ops.sh` (it opens PRs), which no prefix rule
  would predict.

**Domains, by what the skill actually operates on:**

| Domain | Count | Basis |
|---|---:|---|
| Git & code review | ~24 | operates on commits, branches, PRs, review feedback |
| Issue & project tracking | ~10 | operates on tracker issues (GitHub/GitLab/Linear/Jira) |
| Spec & planning | ~9 | operates on spec/plan/task artifacts |
| Code quality & refactor | ~14 | operates on source, per language |
| Security & audit | ~10 | operates on findings, threat surfaces |
| Design (Stitch family) | 15 | operates on Stitch projects — vendored, externally sourced |
| Docs | ~6 | operates on the docs tree |
| Infra & deploy | ~12 | operates on the deployed environment |
| Meta & session | ~8 | operates on Claude's own session/config |

Counts are approximate **by design**: the exact boundary between "code quality"
and "security" moves depending on whether a skill's *subject* or its *verb* is
weighted, and both readings are defensible. That ambiguity is the finding —
**a clean partition does not fall out of the corpus**, and T036's requirement to
"assert the partition" is therefore satisfied by asserting where it fails, not
by forcing a tidy answer.

The partition-breakers, named:

- `repo-clean` — PRs *and* branches; belongs to Git & code review, but
  `issue-triage` overlaps its dedup logic.
- `lifecycle-run` — drives spec → issue → PR → verify; touches four domains by
  construction and cannot sit in one.
- `pr-review` — consumes both `git_ops.sh` and `git_platform.sh` and is the only
  skill in the intersection of the two largest script dependencies.

**Recommendation**: if plugins ship, `lifecycle-run` and `repo-clean` go in a
`manifest-workflows` plugin that depends on the others, rather than being
assigned to one domain and quietly losing half their function.

## T037 — the shared-script dependency graph

Measured by grepping `.apm/skills/*/SKILL.md` for each script name.

| Script | Skills depending on it | Domains spanned |
|---|---:|---|
| `git_ops.sh` | **12** | Git/review, issues, spec/planning, code quality |
| `parallel_agent.py` | 6 | quality, security, spec |
| `git_platform.sh` | **4** | Git/review, infra |
| `tracker_ops.sh` | 3 | issues |
| `issue_support.sh` | 2 | issues |
| `label_sync.sh` | 1 | issues |

`git_ops.sh` consumers: `issue-prep-auto`, `git-commit`, `issue-dev-auto`,
`plan-manage`, `lifecycle-run`, `pr-address-comments`, `pr-merge-stacked`,
`pr-clean-base`, `pr-reset-reapply`, `pr-review`, `repo-clean`,
`shell-refactor`.

`git_platform.sh` consumers: `ci-setup`, `pr-monitor`, `pr-review`,
`repo-clean`.

**22 of 108 skills (20%) depend on at least one shared script.** The other 80%
are self-contained markdown.

### The decision T037 asks for

Three options, and the reason the third wins:

1. **Duplicate the script into every plugin that needs it.** Rejected: 12 copies
   of `git_ops.sh` is 12 things to patch when a platform API changes, and the
   drift this whole feature exists to remove would be reintroduced by design.
2. **Put each script in the plugin of its majority consumer.** Rejected:
   `git_ops.sh`'s consumers span four domains, so any single placement leaves
   three plugins with a cross-plugin dependency APM's plugin model does not
   express.
3. **A `manifest-core` plugin holding the shared scripts, which the others
   depend on.** ✅ **Chosen.** One copy, one place to patch, and the dependency
   is declared rather than implied.

**Caveat that must not be lost**: this is a *recommendation on paper*. Option 3
assumes APM plugins can declare a dependency on another plugin and that a
consuming skill can resolve a script from it at a stable path. **Neither is
measured.** Before packaging, verify both — the same way cell (b) was verified,
against the tool rather than its documentation. If plugin-to-plugin dependency
does not exist, option 3 collapses and the honest answer becomes "skills that
depend on shared scripts cannot be packaged as plugins", which would cut the
plugin story to the 80% that are self-contained.

## What this does NOT do

No plugin is generated, no `apm pack` is run, no script is moved. US4 remains
deferrable, and T038–T040 stay open. This document exists so that whoever picks
US4 up inherits the analysis and the unverified assumption, rather than
rediscovering both.
