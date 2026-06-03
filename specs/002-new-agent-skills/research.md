# Phase 0 Research: New Agent Skills

**Feature**: 002-new-agent-skills | **Date**: 2026-06-01

All spec-level `NEEDS CLARIFICATION` items were resolved during `/speckit-clarify`
(see spec §Clarifications). This document records the design decisions that flow from
those clarifications plus integration/best-practice research for each skill.

---

## R1. Version resolution + integrity hashing per ecosystem (`version-pin`)

**Decision**: Resolve specific versions and integrity hashes by shelling out to each
ecosystem's native tooling, never by guessing. Per-ecosystem mapping:

| File / type | Detect loose | Resolve version | Hash form | Native tool |
|-------------|-------------|-----------------|-----------|-------------|
| `requirements.txt` | no `==`, range only, no `--hash` | `pip index versions` / `pip-compile --generate-hashes` | `--hash=sha256:...` | `pip` / `pip-compile` |
| `docker-compose.{yml,yaml}` | `image: x:latest` or no digest | `docker manifest inspect` | `@sha256:...` digest | `docker` |
| `Dockerfile` | `FROM x:latest` / no digest | `docker manifest inspect` | `@sha256:` digest | `docker` |
| `package.json` / npm | `^`/`~`/`latest` | `npm view <pkg> version` | integrity from `package-lock.json` | `npm` |
| GitHub Actions `uses: org/action@vN` | mutable tag/branch ref | resolve tag → commit SHA | full 40-char commit SHA | `git ls-remote` / `gh api` |

**Rationale**: Native tools produce the same versions/hashes the build will actually use,
avoiding the correctness and maintenance burden of bespoke registry clients. Matches the
user's clarification (native package managers).

**Alternatives considered**:
- Direct registry HTTP APIs (PyPI JSON, Docker Registry v2) — rejected: more per-ecosystem
  bespoke code and divergence risk from what the package manager resolves.
- Lockfile-only — rejected as primary: lockfiles don't always exist for every target file
  (e.g. a hand-written `requirements.txt` without `pip-compile`); used opportunistically.

**Failure mode**: When the native tool is absent or offline, emit a reported warning
(FR-002 / FR-007) and leave the entry unchanged — never a silent skip or partial rewrite.

---

## R2. On-demand auto-fix vs. hook warn-only split (`version-pin`)

**Decision**: Two execution modes from one skill/script:
- **On-demand** (`/version-pin [path]`): resolve + rewrite in place (FR-003a).
- **Hook path** (save of a tracked file): `--check`/warn-only — print violations and the
  exact pinned+hashed replacement line, exit non-zero to surface, but make **no edits**
  (FR-005, spec Clarifications).

**Rationale**: Auto-editing a file mid-edit fights the editor and surprises the user; a
non-mutating advisory is the correct hook posture. The user explicitly chose warn-only on
the hook.

**Hook wiring**: Use the existing `ai-hooks-integration` skill conventions (PostToolUse /
on-write matcher scoped to the recognized file globs) rather than introducing a new hook
framework. Registration must be idempotent (guarded existence check) per Constitution V.

---

## R3. Bypass mechanism (`version-pin`)

**Decision**: Inline trailing comment marker on the entry, ecosystem-comment-aware, e.g.
`requests  # version-pin:ignore reason="vendored build"`. The skill skips the line,
leaves it byte-for-byte unchanged, and lists it under a "Bypassed" group in the summary
(FR-004).

**Rationale**: Inline markers are self-documenting, travel with the line in diffs/blame,
and need no side-car config file. Mirrors widely understood `# noqa` / `# nosec` idioms.

**Alternatives considered**: central allowlist file — rejected for v1 (extra indirection,
drift risk); may be added later as an extension.

---

## R4. Recognized-file rule set is data, not code (`version-pin`)

**Decision**: Express the file→rule mapping as a `version_pin` block in
`command_config.yml` (globs, loose-pattern regexes, resolver command, hash form). The
script reads this block so new file types are added by config, not code (FR-005
"documented, extensible list").

**Rationale**: Consistent with how the repo centralizes policy in YAML
(`labels.yml`, `command_config.yml`); keeps the skill extensible without script edits.

---

## R5. Reuse existing platform abstraction (`pr-review`, `branch-clean`)

**Decision**: `pr-review` enumerates PRs via `git_ops.sh pr-list` / `pr-view` / `pr-diff`
/ `pr-checks` (already implemented for github + gitlab) and `git_platform.sh` for
detection. `branch-clean` uses `git` plumbing directly (`git branch --merged`,
`git for-each-ref ... [gone]`, `git log -1 --format=%cr`) and `git_platform.sh` only when
the explicit remote-deletion flag is set.

**Rationale**: Avoids duplicating platform logic; respects Constitution IV (no core-script
bloat — these are sibling scripts). Note the *existing* `git_ops.sh pr-review` subcommand
submits a review to one PR — distinct from the new `pr-review` skill which triages *all*
open PRs read-only; naming overlap is acceptable since they live at different layers.

**Best practice — "is it needed?" signals** (FR-013): per PR collect → mergeable state,
CI/checks status, age since last activity, branch already merged into base, title/branch
duplication of another open PR, draft flag. Disposition heuristic: merged-or-superseded →
*close candidate*; failing/conflicting → *needs-rebase*; clean + approved → *merge*; else
*keep*.

---

## R6. Branch-clean safety model (`branch-clean`)

**Decision**: Candidate categories: (a) merged into default branch (`git branch --merged
<default>`), (b) `[gone]` upstream (`git for-each-ref --format '%(refname:short) %(upstream:track)'`),
(c) stale > threshold (last commit date). Default scope **local only**; remote deletion
behind `--include-remote` (spec Clarifications, FR-016a). Always exclude default,
configured protected branches, and current `HEAD` (FR-017). Dry-run preview is the default;
deletion requires `--apply` + confirmation (FR-018). Unmerged branches never enter the
"merged" category and are never force-deleted by the default path (FR-020).

**Rationale**: Deletion is destructive and remote deletion affects shared state; safest
defaults with explicit opt-in. Overlaps conceptually with the `commit-commands:clean_gone`
plugin command but is platform-aware, grouped-by-reason, and dry-run-first.

**Protected-branch source**: read from a `branch_clean.protected` list in
`command_config.yml`, defaulting to the detected default branch + common release globs
(`release/*`, `main`, `master`).

---

## R7. Docs orchestration ordering (`docs-all`)

**Decision**: Dispatch `docs-readme`, `docs-diagrams`, `docs-improve` as independent
sub-agents (Agent tool / parallel where safe). Choose order per run from changed-file
signals; documented **default precedence** fallback: `docs-readme` → `docs-diagrams` →
`docs-improve` (establish facts → visualize structure → quality-pass the whole set last).
Hard dependency honored: `docs-improve` runs after `docs-readme`/`docs-diagrams` so its
Diataxis audit sees their output. One consolidated report states order + rationale +
per-sub-agent outcome; a failing sub-agent is surfaced, others continue (FR-008–011).

**Rationale**: Matches the user's "decide per run with documented default" choice.
Improve-last maximizes the surface the quality pass evaluates.

**Alternatives considered**: fixed static order — rejected per clarification; fully
parallel with no ordering — rejected because `docs-improve` depends on prior outputs.

---

## R8. Skill authoring + deployment conventions (all four)

**Decision**: Each skill is `.skillshare/skills/<name>/SKILL.md` with `name` +
`description` frontmatter (Constitution IV). Tool policies added to
`command_config.yml.tool_policies`; validation overrides to
`validation_criteria.yml.command_overrides`. Deployment relies on existing
`deploy_home_skills` in `bootstrap.sh` — no new install step. `configs/claude/skills`
stays a symlink.

**Tool-policy decisions**:
- `version-pin`: `Read, Glob, Grep, Bash, Edit/Write` (must rewrite files); Tier 1 (security/supply-chain).
- `docs-all`: `Read, Glob, Grep, Agent` (orchestration); Tier 2.
- `pr-review`: `Read, Glob, Grep, Bash` (gh/glab read-only); Tier 2; mcp: none required.
- `branch-clean`: `Read, Glob, Grep, Bash`; Tier 1 for the destructive `--apply` path (breaking-changes/error-handling gates), Tier 2 for dry-run.

**Rationale**: Aligns with existing entries (e.g. `refactor-shell` allows Bash for tooling).
`version-pin` is the only skill granted Edit/Write because it is the only one that mutates
non-config files; the others are read-only or gated.

---

## Open items deferred to planning/tasks (non-blocking)

- Exact `bats` fixtures per ecosystem (Phase 1 / tasks).
- Whether a tiny Python YAML helper is needed for `docker-compose` parsing vs. pure-shell
  (decide during implementation; prefer shell, fall back to Python per repo convention).
