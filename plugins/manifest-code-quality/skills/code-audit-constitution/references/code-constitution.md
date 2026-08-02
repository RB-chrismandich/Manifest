<!-- doc-type: reference -->
# Code Constitution

> Thirteen articles that must hold for every file created or modified, in every
> supported language. Read before writing code — not after review.

**Last Updated**: 2026-07-29
**Audience**: AI assistants and contributors writing or modifying source
**Purpose**: State the pre-write doctrine once, so every language annex, hook,
and automated check derives from the same source

Adjacent machine copy: `../config/code_constitution.json`. Language annexes:
[python](constitution/python.md) · [node](constitution/node.md) ·
[go](constitution/go.md) · [shell](constitution/shell.md) ·
[terraform](constitution/terraform.md).

---

## How this differs from the other two registries

| Registry | Direction | Answers |
|---|---|---|
| `code_constitution.json` | Proactive, pre-write | What must be true of this change? |
| `knowledge_base.yml` (`ANTI-*`) | Reactive, post-failure | What went wrong here before? |
| `validation_criteria.yml` | Verdict, at review | Does this pass Tier 1/Tier 2? |

An article never restates an antipattern; it cites the `ANTI-*` entries it
subsumes so the detection cue stays in one place.

## Enforcement

Four layers, all driven by the same YAML. None of them is optional, and none of
the first three blocks you mid-thought:

| Layer | Mechanism | Blocks? |
|---|---|---|
| Pre-write | `constitution_hook.py` — PreToolUse on `Write\|Edit`, injects the articles and the file's live measurements | no |
| Post-write | `constitution_check.py` via `lint_on_edit_hook.sh` | no |
| Commit | `constitution-check` pre-commit hook | yes |
| CI | the changed-files pre-commit gate | yes |

Advisory checks (`C-TYPE`, `C-TEST`, `C-STRUCT`, `C-DOC`) report at every layer
but never fail the gate — they are heuristics, and a heuristic that blocks
teaches people to suppress it.

## The conflict rule

An explicit user instruction outranks an article. When you deviate, say which
article and why, in the change itself — a silent deviation is indistinguishable
from not knowing the rule.

---

## Article I — CON-001 — Search before you write

> Before adding a function, constant, model, or module, search the codebase for
> one that already does the job and extend it instead of forking it.

**Why**: every duplicate implementation is a future divergence. The second copy
is written because the first was not found, and it is the *finding* that has to
become routine, not the discipline of remembering.

**Before you write**:

- Grep the symbol, then the concept, then the string literal you were about to add.
- Check the shared/util/common module for the language before creating one.
- If an existing implementation is 80% right, extend it or parameterize it;
  opening a second one requires a stated reason.

**Automated**: none. No checker can prove you searched. This is the article the
pre-write hook exists to make unavoidable.

## Article II — CON-002 — One reason to change

> Every file, class, and function has one responsibility; when it crosses the
> size ceiling for its language, split it along a seam rather than raising the
> ceiling or suppressing the warning.

**Why**: a god class is not bad because it is long — it is long because it
absorbed responsibilities that had nowhere else to go. The ceiling is a
tripwire that forces the seam question early, while the split is still cheap.

**Before you write**:

- Name the file's one responsibility in a sentence with no "and" in it.
- If the new code does not fit that sentence, it belongs in a different file.
- When splitting, cut along the dependency seam (I/O vs. logic, parse vs.
  render, policy vs. mechanism) — never at the halfway line.

**Automated**: `C-SIZE`, using the per-language ceilings in the annex. Ceilings
are set against this repo's measured distribution per language, and each annex
states the measurement its numbers were drawn from — they are not uniform, and
where a ceiling sits below the measured p95 (shell, whose p95 is 1091 lines)
that is a deliberate ratchet, not a description of current practice.

## Article III — CON-003 — Third time, centralize

> Write it once, note the second occurrence, and on the third extract it to a
> shared module every caller imports — never copy a block that already exists
> somewhere else in the repository.

**Why**: the cost of duplication is not the bytes, it is that a fix applied to
one copy silently leaves the others wrong. Three is the threshold because two
occurrences are often coincidence and abstracting on the first is
[CON-006](#article-vi--con-006--extension-by-addition) in reverse.

**Before you write**:

- Search for the block you are about to paste. If it exists, import it.
- On the third occurrence, extract — and delete the other two in the same change.
- Extract behavior, not shape: two blocks that look alike but change for
  different reasons must stay apart.

**Automated**: `C-DUPE` hashes normalized token blocks within and across the
changed files and reports repeats at or above the language's block threshold.

## Article IV — CON-004 — Data is not code

> JSON, YAML, Markdown, HTML, SQL, and prompt payloads live in their own files
> under a `data/`, `templates/`, or `fixtures/` directory and are loaded by one
> loader — never pasted into a source file as a literal.

**Why**: a payload embedded in source is unreviewable (it diffs as one string),
unvalidatable (no schema tooling sees it), untestable in isolation, and
uneditable by anyone who does not read the host language. Externalizing it makes
the payload a first-class artifact: linted, diffed line-by-line, and swappable
without touching logic.

**Before you write**:

- A literal that another tool could parse belongs in a file that tool can read.
- Put it in the language's `data_dirs` (see the annex), name it for its subject,
  and load it through one loader function — not `open()` scattered per call site.
- Interpolated templates count: extract the template, keep the interpolation.
- Legitimately inline: a value short enough to read at a glance, a docstring, or
  a fixture whose whole point is being adjacent to its assertion.

**Automated**: `C-DATA` parses each changed file and flags string literals and
constant collections that exceed the language's payload threshold and parse as,
or structurally resemble, JSON / YAML / Markdown / HTML.

## Article V — CON-005 — Typed, validated boundaries

> Every value crossing a module, process, network, or file boundary is typed and
> validated at the boundary by a declared model, never passed as an untyped
> mapping and never trusted because the caller looked fine.

**Why**: an untyped mapping defers every error to the deepest possible point,
where the context needed to explain it is gone. A declared model turns a class
of runtime bugs into an import-time or request-time error with a field name in it.

**Before you write**:

- Declare the shape: a validated model for external input, a plain typed record
  for internal structure, an enumerated type for a closed set of values.
- Validate once, at the edge; inside the boundary the type is a guarantee.
- Never widen a signature to `Any`/`interface{}`/`object` to make a call site
  compile — that moves the failure, it does not remove it.

**Automated**: `C-TYPE` (advisory) flags public functions that accept or return
an unparameterized mapping at a module boundary.

## Article VI — CON-006 — Extension by addition

> New behavior arrives as a new registry row, plugin, or config entry rather
> than a new branch inside a growing conditional — and the abstraction is
> introduced on the third real case, never speculatively on the first.

**Why**: the two failure modes are symmetric and both expensive. A conditional
that grows a branch per case becomes the one file every feature must edit; an
abstraction built for imagined cases pays a permanent tax for a future that
usually does not arrive.

**Before you write**:

- If you are adding the third `elif`/`case`, replace the chain with a lookup.
- Prefer a data-driven registry the new case *adds a row to*.
- Do not add a parameter, hook, or interface with exactly one implementation
  because a second one might exist someday.

**Automated**: none — the judgement is the whole content of the article.

## Article VII — CON-007 — Errors travel

> Catch the narrowest exception that can occur, attach the context the caller
> needs, and re-raise with the original cause attached; a caught error is never
> logged and dropped, and fail-open is a documented decision with a stated blast
> radius, never a default.

**Why**: a swallowed error converts a loud failure into a silent wrong answer.
Silent wrong answers are the most expensive defect class this repo has measured,
because nothing reports them and the caller proceeds on bad data.

**Before you write**:

- Catch the specific type; a bare or blanket catch needs the reason inline.
- Add context on the way up and preserve the original cause.
- If a handler intentionally continues, say so and state what is lost.
- A check that cannot verify something reports "unverified", never "pass".

**Automated**: `C-ERR` flags blanket catches, catch blocks with no re-raise and
no observable effect, and re-raises that discard the cause.

## Article VIII — CON-008 — Tests first

> A failing test that pins the intended behavior is written and observed failing
> before the implementation, and a new guard is not proven until the source has
> been mutated to the wrong behavior and exactly that test failed.

**Why**: a test written after the code tends to assert what the code does rather
than what it should do, and a guard never watched to fail may be asserting
nothing at all.

**Before you write**:

- Write the test, run it, read the failure message — it is the first user of
  your API.
- Vary the fixture: flat data collapses statistics and passes trivially.
- Mutate the source to the wrong behavior, confirm exactly the new test fails,
  restore, confirm the diff is clean.

**Automated**: `C-TEST` (advisory) reports a new source file with no test at the
mirroring path.

## Article IX — CON-009 — Structure is a contract

> Mirror the layout, module naming, error-output convention, and CLI contract
> already established in the tree, and place each test at the path that mirrors
> the source it covers.

**Why**: consistent structure is what makes a codebase searchable. Every
deviation costs every future reader a lookup, and the cost is paid forever by
people who did not choose it.

**Before you write**:

- Read a sibling module first and match its shape.
- Route errors through the established helper; do not invent a second format.
- Every user-facing entry point answers `--help` before touching config or state.

**Automated**: `C-STRUCT` (advisory).

## Article X — CON-010 — Comments earn their place

> Document the public surface and explain why a non-obvious decision was made;
> delete commented-out code and any comment the adjacent code has already
> outgrown.

**Why**: a comment restating the code is noise that ages into a lie. A comment
explaining a constraint, a rejected alternative, or a non-obvious ordering is
the only place that information exists.

**Before you write**:

- Docstring every public module, class, and function: what it is for, not what
  it does line by line.
- Explain the *why* at the point the reader would otherwise ask.
- Commented-out code is deleted; version control already remembers it.
- Match the comment density of the surrounding file.

**Automated**: `C-DOC` (advisory).

## Article XI — CON-011 — Dependencies are liabilities

> Exhaust the standard library first, evaluate a candidate on maintenance,
> typing, transitive footprint, and license before adopting it, declare bounded
> ranges, resolve them into a committed lockfile, and audit that lockfile for
> known vulnerabilities.

**Why**: every dependency is code you did not write, cannot review at the rate
it changes, and must patch on someone else's schedule. The evaluation is cheap
before adoption and nearly impossible after.

**Before you write**:

- Check the standard library, then the dependencies already present, then PyPI /
  npm / pkg.go.dev.
- Adoption checklist: commits in the last six months, issue triage happening,
  first-class type support, small transitive tree, permissive license.
- Declare bounded ranges in the manifest; pin exact versions in the lockfile;
  commit the lockfile for applications, not for published libraries.
- Install from the lockfile in CI and fail on drift; audit for known CVEs.
- Secrets come from the environment. Never a literal, never a default value.

**Automated**: none here — pinning is enforced by `/version-pin` and the CI
lockfile gate.

## Article XII — CON-012 — Delete before you add

> Remove the dead branch, unused import, superseded config key, and orphaned
> test in the same change that obsoletes them; refactor the shape you need
> before accreting onto the shape you have.

**Why**: dead code is read as live by everyone who did not write it, and it is
the substrate every later duplication grows on.

**Before you write**:

- Removing a feature means removing its config, docs, tests, and registry rows.
- If the change would be clean against a slightly different structure, change
  the structure first, in its own commit.
- Leave no compatibility shim without an expiry stated in the code.

**Automated**: none.

## Article XIII — CON-013 — No arbitrary execution

> Never hand caller-influenced input to an evaluator, a deserializer, or a
> shell, and never assemble a query by string formatting; use the safe
> counterpart and bind parameters instead.

**Why**: these are the sinks where a data-handling bug becomes remote code
execution. Every one of them has a safe counterpart that costs nothing, so the
dangerous form is almost always an accident rather than a decision — which is
exactly why it needs to be caught mechanically rather than remembered.

**Before you write**:

- Parsing a literal? `ast.literal_eval`, never `eval`/`exec`.
- Reading a serialized object? JSON or a schema-validated decoder, never
  `pickle`/`marshal`/`dill`, and `yaml.safe_load` rather than `yaml.load`.
- Running a program? Pass the argv list. `shell=True`, `os.system`, and
  `curl … | sh` all hand a metacharacter parser your input.
- Querying? The statement is a constant and the values are bound parameters.
  An f-string in a query is the defect regardless of where the value came from.
- A genuinely necessary exception is declared inline with its reason.

**Automated**: `C-DANGER` for Python (AST: the call *and* the shape of its
argument, so a constant statement stays silent), plus a narrow line-based set
for shell, TypeScript, and Go.

**Boundary**: this article covers the injection *sinks*. It does not replace the
reactive registry — hardcoded secrets (`ANTI-025`) and unquoted shell expansion
(`ANTI-001`) keep their entries there, and `/ai-code-audit` remains the deep
security pass. What CON-013 adds is that the sinks are now checked before the
code is written rather than after it is reviewed.

---

## Related documents

- [antipatterns.md](antipatterns.md) — reactive guardrail registry (`ANTI-*`)
- [doc-concision.md](doc-concision.md) — the same discipline for documentation
- `docs/CODING_STANDARDS.md` — the tools and gates each language runs
- `.specify/memory/constitution.md` — project governance (distinct from this
  file, which governs source changes)
