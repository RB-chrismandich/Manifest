# Skill Naming Standard

> Naming convention for every skill in `plugins/<bundle>/skills/` — ratified by
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
print
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
automation-rework-breakeven
code-to-design
design-md
enhance-prompt
extract-design-md
extract-static-html
false-green-check-audit
generate-design
help
loop-scaffold
manage-design-system
parallel-agent
pass-cli
react-components
react-native
react-vite-dashboard
remotion
render-verify
review-round
screen-prompts
shadcn-ui
stitch-loop
taste-design
upload-to-stitch
```
<!-- /skill-naming:exceptions -->

| Name | Rationale |
|---|---|
| `ai-hooks-integration` | Vendored from `github.com/runkids/ai-hooks-integration`; not ours to rename. |
| `code-to-design`, `design-md`, `enhance-prompt`, `extract-design-md`, `extract-static-html`, `generate-design`, `manage-design-system`, `react-components`, `react-native`, `react-vite-dashboard`, `remotion`, `shadcn-ui`, `stitch-loop`, `taste-design`, `upload-to-stitch` | Vendored from `github.com/google-labs-code/stitch-skills`; Stitch MCP design/build/utility skills — not ours to rename. |
| `automation-rework-breakeven` | SkillClaw-evolved break-even analysis skill; descriptive compound name encodes the trade-off being modeled. |
| `false-green-check-audit` | SkillClaw-evolved health-check audit; "false green" is the domain term being guarded against. |
| `help` | Universal single-word entry point; ergonomics beat conformance. |
| `parallel-agent` | Harness orchestration is an established user-facing command, not a domain-purpose skill name. |
| `pass-cli` | Named for the `pass-cli` binary it wraps; `token-*` here means LLM token economy, so a credential fetcher must not move there. |
| `loop-scaffold`, `render-verify`, `review-round`, `screen-prompts` | Internal phase names of the `adversarial-design-loop` plugin (merged from #674). They are `<phase>-<noun>` within one closed loop, not catalog-wide verbs, and the plugin's own bodies, README and cross-references key on them. |

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
| `dashboard` | bare noun; no domain, no verb |

## Lifecycle: adding, renaming, retiring

A skill's name and description are **derived into four other places**. Editing
the `SKILL.md` alone leaves the repo in a state CI rejects, so run the
generators in the same commit.

| Command | Writes |
|---|---|
| `configs/claude/scripts/generate_commands_doc.py` | `docs/COMMANDS.md` |
| `configs/claude/scripts/generate_commands_doc.py --inject-guides` | `configs/gemini/GEMINI.md`, `AGENTS.md` (the compact index) |
| `configs/claude/scripts/generate_cursor_rules.sh` | `configs/cursor/rules/*.mdc` |

The two `generate_commands_doc.py` invocations write **different files** — running
the bare form does not update the guides, and that asymmetry is the usual reason
a "just add a skill" commit fails CI.

### Add or rename

1. Create/edit `plugins/<bundle>/skills/<name>/SKILL.md` with `name` +
   `description` frontmatter, and add the skill to that bundle's
   `plugins/<bundle>/.claude-plugin/plugin.json` `skills[]` **and** to
   `configs/claude/config/skill_policies.yml` under the same bundle.
   **Do not edit `.apm/skills/`** — since spec 674 T3.3 it is a *generated*
   mirror (`generate_skill_mirror.sh`, gitignored), and an edit there is
   silently destroyed by the next rebuild. `configs/claude/skills/` is a compat
   symlink to that mirror — also never a real dir, also never edited.
2. Add `tool_policies` in `configs/claude/config/command_config.yml`; add
   `validation_criteria.yml` overrides only if the skill needs them.
3. Run all three generators above and commit what they change.
4. Regenerate the mirror (`configs/claude/scripts/generate_skill_mirror.sh`),
   then verify: `generate_commands_doc.py --check` (exit 1 = drift), then
   `bats tests/bats/context_budget.bats tests/bats/skill_naming.bats
   tests/bats/bundle_partition.bats`. The partition check is the one that fails
   if the skill is in a manifest but not the registry, or in neither.
   Frontmatter across all skills is capped at 29,000 chars — a new skill may
   need a trim pass elsewhere before it fits.
5. Refresh your home with `apm-dev-sync`. `./bootstrap.sh` no longer deploys
   skills — apm has owned `~/.claude/skills` since SC-006.

### Qualified vs bare names

Once a skill ships inside a plugin bundle it is reachable **only** as
`<bundle>:<name>` — `/manifest-docs:docs-all`, not `/docs-all`. There is no bare
alias and no fallback. The bundle is therefore part of the name, and moving a
skill between bundles is a user-visible rename: see
[PLUGIN_RELEASE.md](PLUGIN_RELEASE.md#qualified-names) for what that means for
versioning and for cross-skill references.

### Retire

Deleting the directory is not enough. Also prune: the **Exceptions** block *and*
table above if the name was listed there, its `tool_policies` entry, and any
surviving cross-references (`grep -rn '<name>'`). Then regenerate and verify as
above.

Two traps worth knowing:

- A rename leaves an untracked `__pycache__` behind. The orphan directory trips
  `skill_naming.bats` locally while CI stays green, and makes apm skip the skill
  entirely — it declines any directory holding files it did not place. Remove it
  from the repo *and* `~/.claude/skills`, repo-first.
- Changed `.mdc` files fight `end-of-file-fixer`; `configs/cursor/rules/` is
  excluded from that hook so the generator stays authoritative.

## History

The 2026-07 migration (91 → 88 skills: 68 renames, 2 duplicate merges, 1 deprecated
deletion) is recorded in
[specs/480-skill-naming-taxonomy/rename-map.tsv](../specs/480-skill-naming-taxonomy/rename-map.tsv)
and issue #478 — consult it when tracing an old name.
