# Measured facts — Manifest plugin partition (2026-07-30)

Measured directly, not inferred. Each line names its method.

## M1 — REFUTED. `plugin.json` DOES have a `dependencies` field.

⚠️ **The original M1 below concluded the opposite and is wrong.** It inferred
absence from a corpus survey. A direct probe against Claude Code's own validator
refutes it, and in doing so refutes the central conclusion of
`specs/522-apm-deploy-migration/plugin-partition.md`.

Method: `claude plugin validate --strict <path>` against hand-built manifests.
This is Claude Code's own schema validator, not documentation.

```
"dependencies": {"manifest-core": "^0.1.0"}   -> ✘ dependencies: Invalid input: expected array, received object
"dependencies": ["manifest-core"]              -> ✔ Validation passed
"dependencies": ["manifest-core@manifest"]     -> ✔ Validation passed
"dependencies": [{"name":"manifest-core"}]     -> ✔ Validation passed
"dependencies": [{"name":"manifest-core","version":"^0.1.0"}] -> ✔ Validation passed
"dependencies": ["manifest-core@manifest@0.1.0"] -> ✘ dependencies.0: Invalid input
"dependencies": [123]                          -> ✘ dependencies.0: Invalid input
```

**`dependencies` is an array** whose elements are either a string
(`"name"` or `"name@marketplace"`) or an object (`{"name", "version"}`).

Corroborating: `claude plugin prune|autoremove` exists and is documented as
"Remove auto-installed **dependencies** that are no longer needed", with
`--dry-run` and `--scope`. The runtime resolves and installs dependencies
transitively; there would be nothing to prune otherwise.

**Consequence — the repo's spec must be reopened.**
`plugin-partition.md` states, under a ⛔ heading:

> **There is no dependency field.** … `manifest-core` cannot exist as a plugin
> others depend on, because the manifest format has nowhere to say so.

That was measured against `apm pack`'s *output* — five keys — and then
generalised to the plugin *format*. The generalisation does not hold. `apm pack`
simply does not emit a field that the format supports. **Option 3 in that
document — a `manifest-core` plugin holding shared scripts that the others
depend on — is expressible today**, and the disposition "closed measured-limited,
reopen if apm gains plugin dependencies" rests on a false premise.

Still true, and still worth keeping: no plugin in the 276-entry official
marketplace or the 53 installed `plugin.json` files actually *uses*
`dependencies`. It is supported but unexercised, so install-time resolution
behaviour is **unverified** — see V1 in the open-questions section.

---

### Original M1 (superseded) — corpus survey found no dependency field in use

Method: enumerated every key across all 53 installed `plugin.json` files in
`~/.claude/plugins/cache/**/.claude-plugin/plugin.json`.

Fields observed, with counts:
`name` 53, `description` 53, `author` 51, `version` 27, `keywords` 18,
`repository` 16, `license` 16, `homepage` 8, `commands` 2, `agents` 2,
`mcpServers` 2.

Grep for `dependencies|depends|requires|peerPlugins` across all plugin.json and
marketplace.json: **zero hits**.

Every plugin needing a helper ships its own copy under `scripts/`
(observed: chrome-devtools-mcp, ralph-loop, remember, superpowers, vercel).

**Consequence**: `specs/522-apm-deploy-migration/plugin-partition.md` recorded this
as an `apm pack` limitation and left open "reopen if apm gains plugin
dependencies". That framing is wrong — the limit is in the Claude Code plugin
format itself. A `manifest-core` plugin that others depend on cannot exist under
any packager. Option 3 in that document is dead, permanently.

## M2 — Skill frontmatter budget is 92.6% consumed

Method: summed `name` + `description` frontmatter length across all 108
`.apm/skills/*/SKILL.md`.

- Total: **26,860 chars** (~6,715 tokens) against the `tests/bats/context_budget.bats`
  cap of **29,000**.
- Mean 248 chars/skill. Headroom ≈ 2,140 chars ≈ **8 more skills** before the
  gate hard-fails.
- Most expensive: spec-audit-tasks (421), false-green-check-audit (409),
  test-isolate-ambient (377), code-audit-constitution (364), security-review-diff (343).

**Consequence**: this is the strongest argument *for* partitioning. Skills are
rivalrous — budget exhaustion drops descriptions and a name-only skill never
fires. Per-domain installable plugins let a user pay for 2–3 domains instead of
all nine. It is also a hard deadline: the corpus cannot grow ~8 more skills
under the current single-tree model.

## M2b — The budget gate measures the wrong universe; the session sits at ~1.02× of budget

⚠️ **This entry was wrong on first writing and is corrected here.** The first
version claimed 152 plugin skills / 41,273 chars / **1.70× over budget**. That
counted every `SKILL.md` under `~/.claude/plugins/cache/`, which includes
plugins that are cached but **not installed** (vercel, 57 skills, was the
largest single contributor and is not installed) and duplicate version
directories for the same plugin. The corrected numbers are below.

Method (corrected): `claude plugin details <name>` for every plugin in
`claude plugin list` — this is Claude Code's own accounting and reports
"Always-on: ~N tok added to every session". Then a char→token calibration
across the 11 plugins where both numbers are available.

| Source | Skills | Always-on tokens | Method |
|---|---:|---:|---|
| Installed plugins (26 listed, 15 with skills) | 58 | **3,469** | measured by `claude plugin details` |
| Manifest `.apm/skills` | 108 | **~6,700** | 26,860 chars ÷ calibrated 4.01 chars/tok |
| **Live session total** | **166** | **~10,170** | |

Calibration: 11,740 chars / 2,927 measured tokens = **4.01 chars per always-on
token**, which matches the standard heuristic. Per-plugin ratios vary widely
(0.7–13.7) only because the glob picks up version dirs that are not the loaded
one; the aggregate is sound.

`skillListingBudgetFraction` is **0.05** (already the raised, skill-heavy value;
default 0.01) → ~10,000 tokens of listing budget against a 200K context.

**~10,170 needed / 10,000 available ≈ 1.02×.** At the ceiling, not 70% over.

What survives the correction, and it is still the core argument:

1. **Manifest alone is 6,700 of the 10,000-token budget — 67%.** There is
   essentially no headroom for the user's own skills or for more plugins. The
   session is at the cap today.
2. **On the default `skillListingBudgetFraction` of 0.01 (2,000 tokens),
   Manifest alone is 3.35× over.** Any user who installs Manifest without
   knowing to raise that setting gets a corpus where most descriptions are
   dropped, and a name-only skill never fires. This is the number that matters
   for anyone who is not this repo's author.
3. **`tests/bats/context_budget.bats` still measures the wrong universe.** Its
   29,000-char cap counts only `.apm/skills` and is blind to installed-plugin
   skills competing in the same budget. It reports healthy headroom
   (26,860 < 29,000) while the real session listing is at 102% of budget.

The direction of the argument is unchanged — shipping 108 skills to a user who
needs nine is the problem — but the honest magnitude is "at the ceiling", not
"70% over".

## M3 — Only 41% of skills are self-contained, not 80%

Method: counted `.apm/skills/*/SKILL.md` containing none of
`~/.claude/`, `configs/claude/`, `manifest parallel-agent`, `.apm/`.

- **44 / 108 (41%) self-contained.**
- 42 / 108 reference `~/.claude/` hardcoded home paths.
- 38 invoke `manifest parallel-agent` (a PATH binary, `~/.local/bin/manifest`).

**Consequence**: `plugin-partition.md` claims "22 of 108 skills (20%) depend on
at least one shared script. The other 80% are self-contained markdown." Both
numbers are wrong. It counted only six named shell scripts and missed the
`manifest` CLI, the config files, and the state directories.

## M4 — The coupling is to a deployed HOME, not just to scripts

Method: extracted every distinct `~/.claude/...` target referenced across all
SKILL.md files. **62 distinct targets.**

Three kinds, all equally fatal to portability:

| Kind | Examples | Refs |
|---|---|---:|
| Scripts | `git_ops.sh` 26, `learning_capture.sh` 25, `branch_clean.sh` 8, `pr_review.sh` 6, `command_catalog.py` 6, `version_pin.sh` 5, `skillclaw_promote.sh` 5, `deploy_reconcile.sh` 4, `ci_platform.sh` 4, `apm_ownership_report.sh` 4 | — |
| Config | `knowledge_base.yml` 8, `services.yml` 6, `labels.yml` 6, `agent_roster.yml` 6, `tracker_triage.yml` 3, `skillclaw.yml` 3, `mcp_servers.yml` 3, `command_config.yml` 3 | — |
| State | `.plans/` 3, `.agent_outputs/` 3, `settings.json` 4, `skills` 4 | — |

The plugin-structure spec explicitly forbids this form:

> **Never use**: Hardcoded absolute paths … **Home directory shortcuts (`~/plugins/...`)**

**Consequence**: converting a coupled skill to a plugin is not a file move. Each
reference must become `${CLAUDE_PLUGIN_ROOT}/...` and the target must be
duplicated into that plugin — because of M1 there is nowhere shared to put it.
`git_ops.sh` alone has 12 consumers spanning 4 domains, so a domain partition
duplicates it 4 times. That reintroduces precisely the drift feature 522 exists
to remove.

## M6 — A marketplace entry can publish a SUBSET of a skills tree with no plugin.json

Method: enumerated all 276 entries in the official marketplace at
`~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json`.

Entry field frequencies: `name` 276, `description` 276, `source` 276,
`category` 262, `homepage` 260, `author` 191, `strict` 15, `version` 14,
`lspServers` 12, `skills` 4, `tags` 3, `displayName` 3, `keywords` 1.
Top level: `$schema`, `name`, `description`, `owner`, `renames`, `plugins`.
Source kinds: `url` 142, `git-subdir` 79, bare string 53, `github` 2.

`strict: false` appears on exactly 15 entries, and every one of them declares its
components **inline in the marketplace entry** instead of relying on a
`plugin.json` in the source: 12 LSP entries use `strict:false` + `lspServers[]`,
and 3 skill bundles use `strict:false` + `skills[]`.

The decisive example:

```json
{
  "name": "amd-skills",
  "source": {"source": "git-subdir", "url": "https://github.com/amd/skills.git",
             "path": "skills", "ref": "main", "sha": "d93e3ed…"},
  "strict": false,
  "skills": ["./local-ai-use", "./local-ai-app-integration",
             "./serving-llms-on-instinct", "./tracelens-analysis-orchestrator"]
}
```

`skills[]` **selects a subset** of skill directories from the source path. AMD's
repo has more skills than the four listed.

**Consequence — this dissolves the central problem.** Manifest does not have to
move a single file to ship domain plugins. It can publish N marketplace entries
that all point at the *same* `.apm/skills` tree via `git-subdir`, each selecting
a different domain's skill directories with `strict:false` + `skills[]`.

- `.apm/skills/` stays the single source of truth — feature 522's whole point survives.
- No script duplication, because no plugin owns a `scripts/` copy (M1 becomes moot for this path).
- Users install only the domains they need, which is the only real fix for M2b.
- Every gate in the repo (skill_naming, context_budget, docs generators, tool_policies)
  keeps operating on the unchanged tree.

The cost: skills published this way still carry their `~/.claude/...` references
from M4, so they require `bootstrap.sh` to have run. That becomes a documented
prerequisite in each entry's `description`, not an architectural blocker — and
it is already true of the 108 skills today.

The 44 self-contained skills from M3 are the ones that could *additionally*
become true standalone plugins with their own `plugin.json` later. That is a
second, optional step, not a prerequisite.

## M7 — The published marketplace schema URL is dead

Method: `WebFetch https://anthropic.com/claude-code/marketplace.schema.json` → **HTTP 404**.

The official marketplace declares `"$schema": "https://anthropic.com/claude-code/marketplace.schema.json"`
and that URL does not resolve. Any validation Manifest writes must be against the
observed corpus (M6), not against a fetched schema. Do not add a `$schema` key
that points at a 404.

## M5 — The one plugin that exists is not in any commit

Method: `git log --all --diff-filter=A -- 'plugins/*' '.claude-plugin/*'` → empty.

`adversarial-design-loop` (6 skills, 2 agents, 0 commands, 0 hooks, 0 MCP) plus
`.claude-plugin/marketplace.json` (marketplace name `manifest`) exist only as
staged, uncommitted work in the sibling worktree
`emdash/rich-tools-obey-8eua4`. Nothing was touched there.

Notably it is **100% self-contained** — no `~/.claude/` references — which is
why it works as a plugin. It is the existence proof for what a Manifest plugin
has to look like.

## M8 — A plugin skill is reachable ONLY as `<plugin>:<skill>`

Method: direct invocation against claude 2.1.220. `writing-rules` is a skill
provided by the installed `hookify` plugin.

```
$ claude -p '/writing-rules'                              -> Unknown command: /writing-rules
$ claude -p '/hookify:writing-rules reply only READY'      -> READY
```

**Consequence — this is the dominant cost of a hard cutover, and nothing in the
partition analysis anticipated it.** Moving 108 skills into bundles renames all
108 slash commands: `/git-commit` becomes `/manifest-forge:git-commit`. There is
no bare alias; the binary's short-form path is gated on suffix-uniqueness across
plugins, so no alias two same-suffix bundles could later collide on is a stable
contract.

The severe half is internal, not ergonomic. Measured across `.apm/skills/*/SKILL.md`:

> ⚠️ **CORRECTED 2026-07-30 — the original strict/loose figures below are both
> wrong, and they were wrong in opposite directions.** Superseded by the
> re-measurement that follows. Original text retained as the record:
>
> - ~~**Strict** (bare `/name`, excluding backticked and path-like forms): 1
>   skill, 4 references — `code-to-design` → `/extract-design-md`,
>   `/extract-static-html`, `/manage-design-system`, `/upload-to-stitch`.~~
> - ~~**Loose** (any `/name` occurrence): **15 skills, 23 distinct pairs, 33
>   occurrences.**~~

**What the two original figures actually counted.** The *strict* number was not
measuring slash commands at all: `code-to-design` contains **no** `/extract-…`
token. Its four hits are relative markdown FILE links —
`[skills/extract-static-html/SKILL.md](../extract-static-html/SKILL.md)` — a
third reference class that is neither a slash command nor an absolute path. The
*loose* number conflated two genuinely different classes into one figure, which
matters because a `/<name>` grep gate can only ever catch one of them.

**Re-measurement, `.apm/skills/*/SKILL.md` plus sidecars, 2026-07-30:**

| Class | Form | Occurrences | Skills | Caught by a `/<name>` grep? |
|---|---|---|---|---|
| **A** slash-form | `` `/project-verify` `` | 19 (+3 in 2 sidecars = 22) | 10 | ✅ |
| **B** dispatch prose | ``run `docs-improve-readme` `` | 14 | 10 | ❌ |
| **A+B must-fix** | — | **33** (36 incl. sidecars) | **18** (19 incl. sidecars) | — |
| **C** see-also pointer | ``see also `pr-review` `` | 79 | 32 | ❌ (cosmetic) |
| **D** relative link | `../extract-static-html/SKILL.md` | 4 | 1 | ❌ (survives — see below) |

The original "33" was numerically right by coincidence: it is A+B. But it was
labelled as slash calls, and only A carries a slash. **Class B is invisible to
the gate the plan originally specified**, and Class B is where `docs-all`
lives — the skill that dispatches `docs-improve-readme`,
`docs-generate-diagrams` and `docs-improve` as sub-agents by bare name and then
prints a per-skill success table. "15 skills" was an undercount of the union,
which is 18.

Class D survives the cutover as currently partitioned: all five participants
(`code-to-design` and its four targets) are in `stitch-design`, so they remain
siblings under `plugins/stitch-design/skills/` and the links still resolve. It is
recorded as a **partition invariant**, not a defect — see cutover-plan.md T3.6.

`issue-dev-auto` and `lifecycle-run` are autonomous loops. Post-cutover each such
call is an `Unknown command`, the sub-agent improvises, and the loop reports
success — no error, no log line. Honest severity: of the 19 Class-A sites, some
are prose references that break the reader rather than a sub-agent
(`code-audit-constitution:113` "Pinning mechanics are `/version-pin`'s job";
`pr-monitor:36` "the user at `/git-commit`"). The genuinely silent-failure sites
are `issue-dev-auto` :52/:81, `lifecycle-run`, and the `docs-all` /
`code-to-design` delegation chains — roughly a dozen, not 33.

## M9 — `~/.claude/skills/.deployed-skills` is already wrong today

Method: diffed the manifest against the directory listing.

```
on disk: 109   listed: 108
on disk but NOT listed:  README.md, code-audit-constitution
listed but NOT on disk:  print-tune-bambu
```

`code-audit-constitution` was added in the current working tree;
`print-tune-bambu` was retired 2026-07-28 but is still claimed.

**Consequence**: any cutover step that decides what to delete by reading
`.deployed-skills` would leave `code-audit-constitution` behind as a live
user-dir copy, double-loading against its plugin twin, silently over budget —
**with a green deploy**. This is a pre-existing bug independent of the cutover
and should be fixed regardless.

## M10 — Correction: the sibling-home blast radius is smaller than first stated

Earlier in this session I wrote that emptying `~/.claude/skills` "silently strips
108 skills from **five** non-Claude assistants". That overstates what is measured.

What **is** verified on disk: all four symlinks exist and point at the same tree.

```
~/.cursor/skills      -> ~/.claude/skills
~/.gemini/skills      -> ~/.claude/skills
~/.codex/skills       -> ~/.claude/skills
~/.antigravity/skills -> ~/.claude/skills
```

What is verified as an actual *consumer*: **Devin only.** `agent_roster.yml`
records (2026-07-29, devin 3000.2.17) that `devin skills list` enumerates
`~/.claude/skills/<name>/SKILL.md` and returns zero when
`read_config_from.claude=false`.

For Cursor, Gemini, Codex and Antigravity, nothing in the repo measures that they
read `<home>/skills` at all — their skill catalogs demonstrably arrive by a
different route (a generated index in `GEMINI.md`/`AGENTS.md`, one `.mdc` per
skill in `configs/cursor/rules/`), and `bootstrap/lib/deploy.sh` records that
`agy` reads `~/.gemini/config` and never `~/.antigravity`.

**Consequence**: the shared tree must still move (Devin alone forces it), but if
a nonce-differential probe returns INERT for the other four, the four repointed
symlinks can simply be deleted and Phase 2 shrinks substantially. The probe is a
prerequisite, not an optimisation.

## M11 — `skillOverrides` exists and excludes plugin skills

Method: settings schema extracted from the Claude Code binary (v2.1.220).

`skillOverrides` is `record(string, enum(["on","name-only","user-invocable-only","off"]))`
— per-skill listing overrides keyed by skill name. The resolver short-circuits:

```js
if (e.type !== "prompt" || e.source === "plugin") return "on";
```

So an override can suppress a **user-dir** skill while its **plugin** twin stays
fully live — exactly the primitive a phased migration would want.

Also established: **no setting or env var relocates or disables the user skills
dir.** The surface is `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS`,
`CLAUDE_CODE_DISABLE_POLICY_SKILLS`, `CLAUDE_CODE_SYNC_SKILLS`,
`CLAUDE_CODE_PLUGIN_CACHE_DIR`, `CLAUDE_CODE_PLUGIN_SEED_DIR` — there is no
`CLAUDE_CODE_SKILLS_DIR`. Only `CLAUDE_CONFIG_DIR` moves it, and that moves all
of `~/.claude`.

The cutover plan **rejects** using `skillOverrides` for the migration — it needs
a third 108-key registry, and `off` makes the bare name a hard `Unknown command`,
so mid-migration half the catalog answers to `/x` and half to `/bundle:x`. Recorded
because it is the only in-place suppression mechanism that exists.
