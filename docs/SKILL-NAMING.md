# Skill Naming Standard

> Naming convention for every skill in `.skillshare/skills/` — ratified by
> [specs/480-skill-naming-taxonomy](../specs/480-skill-naming-taxonomy/spec.md)
> (issue #478), enforced by `tests/bats/skill_naming.bats`.

**Last Updated**: 2026-07-02
**Audience**: Contributors and AI assistants adding or renaming skills
**Purpose**: Keep skill names predictable, lexicographically clustered by domain, and
enforceable by CI

---

## The Pattern

```text
<purpose>-<verb>[-<qualifier>]
```

- **purpose** — WHAT the skill is about: a domain token from the closed vocabulary
  below (`pr`, `docs`, `shell`, …). Multi-token purposes are allowed only when listed
  (e.g. `ai-code`).
- **verb** — WHAT the skill does: an action verb (`audit`, `review`, `triage`,
  `refactor`, `compress`, `check`, `sync`, …).
- **qualifier** — optional disambiguator when the domain+verb pair is ambiguous
  (`pr-triage-bots`, `shell-audit-pipefail`).

Rules:

1. Lowercase `a-z0-9` tokens joined by single hyphens; 2–4 tokens total.
2. The name must begin with a vocabulary domain token (see below).
3. The skill's frontmatter `name:` must equal its directory name.
4. A suite that fans out to every skill in its domain uses the `-all` qualifier
   (`docs-all`). Umbrella (orchestrating) skills carry **no** special marker otherwise.
5. Language domains are first-position purposes: `python-refactor`, `go-refactor` —
   never `refactor-python` or `code-refactor-go`.

## Front-Matter Style

The `description:` is always-loaded triggering text (injected every session) and
is byte-counted by `tests/bats/context_budget.bats`. Keep it efficient:

- **Inline single-line.** No `|` (literal) or `>` (folded) block scalars — their
  indentation is pure byte overhead in always-loaded context.
- **Quote when needed.** Double-quote the value if it contains a colon followed
  by a space, or begins with a YAML indicator (`- ? : [ ] { } # & * ! | > ' " % @`)
  or a backtick. Escape embedded double quotes as `\"`.
- **~290-char soft norm.** Not a hard cap (the only hard gate is the total-bytes
  budget), but stay near it. If a genuinely-new skill pushes the total over the
  cap, do a set-wide trim before raising the budget.
- **Never trim away** security keywords, negative-space cross-references
  ("Analysis-only; use `X` instead"), the name-match cue, or the primary
  "use when" phrase — these are what make the skill trigger correctly and
  keep siblings from firing.

## Domain Vocabulary

The first token(s) of every skill name must appear in this list. The conformance test
parses the fenced block between the markers — keep one token per line.

<!-- skill-naming:domains -->
```text
a11y
ai-code
automation
antipattern
api
branch
cache
ci
cli
code
config
data
deploy
design
docker
docs
env
git
go
issue
learning
lifecycle
llm
mcp
memory
metrics
node
performance
plan
pr
premise
process
project
prompt
python
repo
security
session
shell
skill
smoke
spec
speckit
terraform
test
token
ux
version
```
<!-- /skill-naming:domains -->

### Adding a new domain token

Add a token only when a skill genuinely fits no existing domain. Add it to the block
above (alphabetical), justify it in the PR description, and prefer reusing an existing
altitude (e.g. a new language gets its own token, like `go`; a new artifact type joins
an existing domain if one fits).

## Exceptions

The only names allowed to bypass the pattern. Each entry needs a rationale here; the
conformance test parses the fenced block.

<!-- skill-naming:exceptions -->
```text
ai-hooks-integration
graphify
help
pass-cli
```
<!-- /skill-naming:exceptions -->

| Name | Rationale |
|---|---|
| `ai-hooks-integration` | Externally installed via skillshare (`github.com/runkids/ai-hooks-integration`); not ours to rename. |
| `graphify` | Named for the managed `graphify` CLI it wraps (`--enable-graphify` toggle, installed binary). |
| `help` | Universal single-word entry point; ergonomics beat conformance. |
| `pass-cli` | Named for the `pass-cli` binary it wraps; `token-*` here means LLM token economy, so a credential fetcher must not move there. |

## Examples

| Good | Why |
|---|---|
| `pr-triage-bots` | purpose `pr`, verb `triage`, qualifier `bots` |
| `shell-audit-pipefail` | clusters with the other `shell-audit-*` skills |
| `python-refactor` | language-first altitude (rule 5) |
| `docs-all` | domain suite (rule 4) |

| Bad | Why |
|---|---|
| `triage-bot-pr-flood` | verb-first; doesn't cluster with `pr-*` |
| `refactor-python` | wrong altitude (rule 5) |
| `pin-known-bug-test-survives-fix` | sentence-like; >4 tokens; verb buried |
| `dashboard` | bare noun; no domain, no verb |

## History

The 2026-07 migration (91 → 88 skills: 68 renames, 2 duplicate merges, 1 deprecated
deletion) is recorded in
[specs/480-skill-naming-taxonomy/rename-map.tsv](../specs/480-skill-naming-taxonomy/rename-map.tsv)
and issue #478 — consult it when tracing an old name.
