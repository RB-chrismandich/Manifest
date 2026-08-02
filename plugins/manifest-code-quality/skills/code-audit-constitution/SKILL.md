---
name: code-audit-constitution
description: Audit and remediate code against the Code Constitution (CON-001..013) — "audit this against the constitution", "is this file compliant", "split this god class". Edits files; judges what no checker can prove. <lang>-refactor is read-only; constitution_check.py only measures.
---

# Constitution Audit and Remediation

The remediation pass the automated checker cannot do.

`constitution_check.py` measures five things well (size, duplication, embedded
payloads, error handling, structure) and cannot do the other two: it cannot
judge the four articles with `checks: []`, and it cannot perform an extraction
or a split. This skill is that second half.

**This skill edits files.** That is what separates it from `python-refactor`,
`node-refactor`, `go-refactor`, `shell-refactor`, and `terraform-refactor` —
those produce a roadmap and touch nothing. Here you change the source, and every
change ends with the checker re-run and the tests green.

Read first, do not restate:

- `configs/claude/references/code-constitution.md` — the universal articles
- `configs/claude/references/constitution/<lang>.md` — the annex for the
  language you are touching (thresholds, `data_dirs`, toolchain)
- `configs/claude/config/code_constitution.yml` — the machine copy

---

## Step 1 — Measure the whole picture

```bash
python3 configs/claude/scripts/constitution_check.py --no-baseline <target>
```

`--no-baseline` is the correct flag **for an audit**, and the wrong one for a
gate. The baseline (`configs/claude/config/constitution_baseline.json`) is a
ratchet: it records the violation count each file already carried when the
constitution was adopted, and the commit hook only fails when a count *rises*.
That is exactly right for a pre-commit gate — nobody should be blocked on debt
they did not write — and exactly wrong here, because the pre-existing debt *is
the work*. Run without it and you see the whole surface.

Add `--strict` to fold the advisory checks (`C-TYPE`, `C-TEST`, `C-STRUCT`,
`C-DOC`) into the blocking set, and `--format json` when you want to sort or
group findings mechanically.

Exit codes: `0` clean, `1` blocking findings, `2` usage or registry error. A `2`
means you passed a bad flag or check id — fix the invocation, do not interpret
the output.

Findings look like this (real output, `--no-baseline`):

```text
.apm/skills/ai-hooks-integration/scripts/install_opencode_plugin.py:124: error: [C-DATA/CON-004] `TEMPLATE_ADVANCED` embeds a 206-line structured payload as a literal
configs/claude/scripts/agents/cli.py:132: error: [C-SIZE/CON-002] function `build_parser` is 73 lines (ceiling 60)
```

Record the counts per check now. They are the before-number you will compare
against in Step 5.

## Step 2 — Judge the four articles no checker can reach

`CON-001`, `CON-006`, `CON-011`, and `CON-012` carry `checks: []` in
`code_constitution.yml`. That empty list is the reason this skill exists. No
tool can prove a search happened, that an abstraction was earned, that a
dependency was evaluated, or that the thing being replaced was deleted. Work
each one explicitly and write down the answer — an unstated judgement is
indistinguishable from an unmade one.

### CON-001 — Search before you write

For each new function, constant, model, or module in scope:

1. Grep the symbol name, then the concept, then the distinctive string literal.
   Three greps, in that order — the symbol misses renames, the concept misses
   synonyms, the literal catches copies neither found.
2. Check the language's shared/util/common module before concluding nothing
   exists.
3. If an existing implementation is ~80% right, extend or parameterize it.
   Opening a second one is allowed, but the reason goes in the code.

Report per item: `searched <terms> → found <path> (extended | 80% miss, reason)`
or `no prior implementation`.

### CON-006 — Extension by addition

Two symmetric failures, both live:

- **Growing conditional.** Count the branches in each `if/elif` or `switch`
  chain the change touches. At the third real case, replace the chain with a
  lookup — a dict, a registry table, a config row — and make the new case a row
  rather than a branch. This repo's own registries (`tracker_providers.yml`,
  `labels.yml`, `command_config.yml`) are the shape to copy.
- **Speculative abstraction.** Flag every parameter, hook, protocol, or
  interface with exactly one implementation and no second caller in the tree.
  Delete it or inline it; it is CON-012 debt wearing a design pattern's name.

### CON-011 — Dependencies are liabilities

For every dependency the change adds or bumps:

1. Is it in the standard library? Then it is not a dependency.
2. Is an already-present dependency sufficient? Check the manifest before the
   index.
3. Adoption check: commits in the last six months, issues being triaged,
   first-class type support, small transitive tree, permissive license. A miss
   on any of these is a stated trade-off, not a silent one.
4. Bounded range in the manifest, exact pin in the committed lockfile, and a
   vulnerability audit over that lockfile (`pip-audit`, `npm audit`,
   `govulncheck`, `trivy` — the annex names the one for your language).
5. Any secret is read from the environment. Never a literal, never a default.

Pinning mechanics are `/manifest-ops:version-pin`'s job — do not reimplement them here.

### CON-012 — Delete before you add

Grep for the corpse of everything this change supersedes: the dead branch, the
unused import, the superseded config key, the orphaned test, the doc paragraph,
the registry row. Remove them in the *same* change. If a compatibility shim must
survive, its expiry goes in the code beside it.

When the change would be clean against a slightly different structure, change
the structure first, in its own commit — refactor, then add.

## Step 3 — Extract the payloads (CON-004 / C-DATA)

For each `C-DATA` finding, in order:

1. **Identify the payload and classify it.** Read the span. Decide whether it is
   *data* (a fixed structure) or a *template* (structure plus interpolation).
   The checker already draws this line at
   `checks.C-DATA.template_interpolation_ratio` (0.08) and says which it thinks
   it is. Data moves to a data file; a template moves to a template file **and
   keeps its interpolation** — do not flatten a template into data.
2. **Choose the target.** Use the first fitting directory from the language's
   `data_dirs` in `code_constitution.yml` (python: `data`, `templates`,
   `tests/fixtures` — the annex's "payload extraction map" gives the per-kind
   destination and the extension). Name the file for its subject, never for its
   host module.
3. **Write the loader first.** One function — `load_<subject>()` — that returns
   a typed model, not a bare dict (CON-005 applies to the value it hands back).
   One loader, imported by every call site; not `open()` scattered per caller.
   Resolve the path relative to the module, not the process cwd.
4. **Move the data.** Cut the literal into the new file verbatim, then reformat
   to the target syntax. Do not "improve" the content in the same step — a
   content change hidden inside a move is unreviewable and unbisectable.
5. **Update the call sites.** Grep the constant's name across the whole tree,
   including tests and any generator that emits it. Replace each with the loader
   call.
6. **Prove behavior is unchanged with a test that fails before the move.** This
   is the step that makes the extraction safe, and it is the one people skip.
   Write a test that asserts the *loaded* value equals the behavior the old
   literal produced, and run it against the pre-move source: it must fail with
   `ImportError` / `AttributeError` / a missing-file error. Only then apply the
   move and watch it pass. A test written after the move asserts that the move
   happened, which you already knew.

Order matters: loader, then data, then call sites. Moving the data first leaves
the tree broken across steps, and a broken tree hides which step introduced a
regression.

## Step 4 — Split the god objects (CON-002 / C-SIZE)

For each file, class, or function over its ceiling:

1. **Name the responsibilities.** Write the unit's job in one sentence with no
   "and" in it. If you cannot, the conjunctions you needed *are* the
   responsibilities — list them. A unit you cannot name responsibilities for is
   not ready to split; keep reading it.
2. **Find the dependency seam.** Cut where the dependency arrow already points
   one way: I/O against pure logic, parsing against rendering, policy against
   mechanism, CLI layer against the library it calls. Concretely: list each
   method's attribute reads and writes, and look for a subset of methods
   touching a disjoint subset of state. That subset is a class. Never cut at the
   halfway line, and never create a `_helpers` module named after no
   responsibility — that is a second god object with a smaller name.
3. **Extract.** Move the seam-side group into its own module or class. Push the
   dependency in one direction only; if the two halves still import each other,
   you cut across the seam rather than along it — back out and re-cut.
4. **Keep the public surface stable.** Every name callers already import keeps
   working: re-export from the original module, or leave a thin delegator. Verify
   by grepping the tree for the old import paths, then running the full suite
   *without* touching a single caller. If callers had to change, that is a
   separate, deliberate, documented commit — not a side effect of a split.
5. **Re-measure.** Both halves must be under the ceiling. A 700-line file split
   into 400 and 300 satisfies the checker and not the article, if the 400 still
   has two names.

For a long *function* the shape is usually "setup / do / format" — that is three
functions, and the ceiling caught it. For a parameter list over ceiling, the
arguments that always travel together are a record, not arguments.

## Step 5 — Re-run, then exempt only what is genuinely correct

```bash
python3 configs/claude/scripts/constitution_check.py --no-baseline <target>
```

Compare against the Step 1 counts, per check. State the delta. A count that did
not move is a finding you did not fix — say so rather than letting it disappear
into a summary.

Then run the language's tests and linter (the annex's toolchain table names
them) and confirm green. An extraction or a split that the checker likes and the
suite does not is a regression.

Only now, for a finding that survives because inline is genuinely the right
answer, add an exemption **with a reason**, on the line above the span:

```python
# constitution: exempt C-DATA — bootstrap default; the linter cannot read its own config yet
BUILTIN_LIMITS = {...}
```

Rules that are enforced, not advice:

- The marker covers the marked line and the **three** lines below it. It does
  not blanket a function.
- A bare `# constitution: exempt C-DATA` with no reason is itself a finding. The
  checker distinguishes "exempted with a reason" from "exempted silently" on
  purpose.
- The reason states *why this one is correct inline*, not that it is
  inconvenient to move. "Legacy", "TODO", and "too big to change now" are not
  reasons — they are baseline entries.

Never exempt as a first move. An exemption written before an extraction was
attempted is a suppression, and a suppressed article stops being an article.

## Step 6 — Lower the ratchet

Fixed violations should lower the recorded ceiling permanently:

```bash
python3 configs/claude/scripts/constitution_check.py --update-baseline <target>
```

Review the resulting `constitution_baseline.json` diff before committing. Counts
must go **down**. An entry that rises means you added a violation while
remediating — find it. If a rise is genuinely intended, the reason goes in the
commit message; the baseline's own `_comment` field states that contract.

---

## Reporting

Report per article touched, in `CON-NNN` order:

| Field | Content |
|---|---|
| Article | `CON-004 — Data is not code` |
| Before / after | check counts from Steps 1 and 5 |
| Action | extracted / split / deleted / exempted / judged-compliant |
| Evidence | the file:line, the new artifact path, the test that failed first |

For the judgement-only articles the evidence is the search terms, the branch
count, the adoption checklist answers, or the list of things deleted — state
them. "Reviewed, no issues" for CON-001 is the same as not having run Step 2.

Never claim a command passed that you did not run, and quote real output.

## Sub-agent dispatch

When ≥3 independent files or articles exist, dispatch one sub-agent per file to analyze it,
then merge findings; below that, analyze inline. Pick the mechanism per the shared Sub-Agent Selection Rules
(`configs/claude/references/sub-agent-dispatch.md`): native Task sub-agents on Claude, or
`[[skill:parallel-agent]]` / inline on other assistants. Dispatched sub-agents execute their task directly and
do not re-dispatch.

Dispatch on **Sonnet** (`subagent_model: sonnet` in `command_config.yml`) — pass the model
explicitly; inheriting the session's model bills premium rates for fan-out work.

Sub-agents may *analyze* in parallel; the edits from Step 3 and Step 4 are applied in the main
session so two agents never rewrite the same file.
