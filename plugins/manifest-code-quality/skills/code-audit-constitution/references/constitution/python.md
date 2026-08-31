<!-- doc-type: reference -->
# Code Constitution — Python Annex

> What the universal articles mean concretely in Python: the toolchain,
> the ceilings, and the idioms that satisfy each article.

**Last Updated**: 2026-07-29
**Audience**: AI assistants and contributors writing Python
**Purpose**: Make each universal article checkable in Python without restating it

Universal articles: [code-constitution.md](../code-constitution.md).
Adjacent machine copy: `../../config/code_constitution.json` (`languages.python`).

## Toolchain

One tool per job. A second tool for a job this table already assigns is a
regression, not a preference.

| Role | Tool | Rule |
|---|---|---|
| Config + dependencies | `pyproject.toml` | The only source. No `setup.py`, `setup.cfg`, or `requirements.txt` for declaring dependencies. |
| Environment + resolution | `uv` | Creates the venv, resolves, and writes `uv.lock`. `poetry` is acceptable in a project already on it; mixing the two is not. |
| Lint + import sort + format | `ruff` and `ruff format` | Replaces `black`, `flake8`, and `isort` outright. Configured in `pyproject.toml`, never in a sidecar file. |
| Type checking | `pyright` | Runs in CI. `mypy` is acceptable where already adopted; one of them, not both. |
| Tests | `pytest` | Fixtures and `@pytest.mark.parametrize`, not `unittest.TestCase` boilerplate. |
| Vulnerability audit | `pip-audit` | Runs against the lockfile, in CI. |

## Size ceilings (CON-002)

| Unit | Ceiling | Split when |
|---|---|---|
| File | 500 lines | It has two responsibilities you can name separately. |
| Class | 250 lines | It holds state for one thing and behavior for another. |
| Method count per class | 12 | A subset of methods touches a disjoint subset of attributes. |
| Function | 60 lines | It has a "setup / do / format" shape — those are three functions. |
| Parameters | 5 | Three or more travel together — they are a record, not arguments. |
| Nesting depth | 4 | Guard-clause the preconditions and return early instead. |

Measured against this repo: function p50 is 8 lines and p95 is 45, so the 60-line
function ceiling flags the tail rather than the norm. Class p95 is 190 against a
250 ceiling; the two classes over it (`Orchestrator` at 479 lines / 14 methods,
`ValidationEngine` at 398 / 13) are precisely the god objects the article exists
to prevent, and they are the reference examples of what not to grow.

Split along the seam, not the midpoint. The seams that actually hold in Python:
I/O against pure logic, parsing against rendering, policy against mechanism, and
the CLI layer against the library it calls. A `_helpers.py` named after no
responsibility is a second god object waiting.

## Payload extraction map (CON-004)

| Payload | Lives in | Loaded by |
|---|---|---|
| Config, defaults, registries | `config/<subject>.yml` | one `load_<subject>()` returning a typed model |
| Prompt / report / code templates | `templates/<name>.<ext>.tmpl` | `Template(path).render(...)` — extract the template, keep the interpolation |
| Test data | `tests/fixtures/<subject>.json` \| `.yml` | a `pytest` fixture, shared across the modules that need it |
| Generated artifacts | `data/<name>.json` | a generator with a committed output and a drift test |
| SQL | `queries/<name>.sql` | one loader; never string-built from user input |

**Legitimately inline**: a value short enough to read at a glance; a docstring; a
fixture under 40 lines whose whole point is sitting beside its assertion; and a
literal a lint or bootstrap path must read *before* its own config is available —
the case `docs_lint.py` documents inline and keeps small on purpose. Everything
else moves. Where inline is genuinely right, say so on the line above:

```python
# constitution: exempt C-DATA — bootstrap default; the linter cannot read its own config yet
BUILTIN_LIMITS = {...}
```

The failure this article prevents is live in this repo today:
`budget_broker.py` holds a third hand-copied version of the model fallback
chains and has already drifted to `claude-opus-4-8` while `parallel_agent.yml`
and `agents/config.py` both say `claude-opus-5`. One YAML file and one loader
would have made that divergence impossible to express.

## Article annexes

### CON-001 — Search before you write

- `grep` the symbol, then the concept, then the literal string, before adding it.
- Check the standard library first: `pathlib`, `dataclasses`, `enum`,
  `functools`, `itertools`, `contextlib`, `concurrent.futures`, `sqlite3`,
  `tomllib`, and `statistics` remove most reasons to reach for a dependency.
- Then check what the project already depends on. A second HTTP client, YAML
  parser, or retry decorator needs a stated reason.

### CON-003 — Third time, centralize

- The third copy of a constant, chain, or mapping becomes one module-level
  definition every caller imports — and the other two are deleted in the same
  change, not left "for now".
- A comment saying "matching `<other file>`" is an admission that this article
  was skipped. Import the other file instead.

### CON-004 — Data is not code

- Extract by content, not by size: if another tool could parse the literal, it
  belongs in a file that tool can read.
- Code-generation templates count. A 200-line JavaScript plugin embedded as a
  Python string is a `.js.tmpl` asset that no editor can currently syntax-check.
- Load through one function. `open()` at every call site is the same duplication
  the extraction was meant to remove.

### CON-005 — Typed, validated boundaries

- Annotate every parameter and return. `pyright` runs in CI; an unannotated
  public function is an unchecked one.
- `pydantic` models for anything arriving from outside the process — HTTP,
  files, environment, subprocess output. `@dataclass` (usually `frozen=True`)
  for internal records. A bare `dict` crossing a module boundary is the defect.
- `enum.Enum` or `typing.Literal` for closed value sets. A magic string is a typo
  the type checker cannot see.
- Prefer `X | None` over `Optional[X]`, and `collections.abc` over `typing` for
  `Sequence`/`Mapping`/`Iterable`.

```python
# wrong — untyped mapping crossing a boundary, magic strings, no validation
def charge(order, mode="standard"):
    return order["amount"] * RATES[mode]

# right — declared shape, closed value set, validated once at the edge
class Mode(StrEnum):
    STANDARD = "standard"

def charge(order: Order, mode: Mode = Mode.STANDARD) -> Decimal:
    return order.amount * RATES[mode]
```

### CON-006 — Extension by addition

- Replace the third `elif` with a dict lookup or a registry the new case adds a
  row to.
- Prefer small pure functions and composition over a class hierarchy. A class
  with one method and no state is a function.
- Do not add a parameter, hook, or protocol with exactly one implementation.

### CON-007 — Errors travel

- Never `except:` and never a bare `except Exception:` without a stated reason
  on the line above it.
- Catch the specific type, add context, and preserve the cause:
  `raise ConfigError(f"...{path}") from err`.
- `logger.exception(...)` followed by `pass` or `return None` is the swallowed
  failure this article names. Either the caller learns, or the function
  documents what was lost.
- Every file, socket, subprocess, lock, and connection is acquired with `with`
  or a `@contextmanager` — cleanup that depends on reaching the end of a
  function does not survive the first exception.

### CON-008 — Tests first

- Write the failing test, run it, read the message, then implement.
- `@pytest.mark.parametrize` for the case table; fixtures for shared setup;
  `tmp_path` and `monkeypatch` instead of touching the real environment.
- Vary the fixture data — flat inputs collapse any statistic to zero and pass
  assertions that are testing nothing.
- Mutate the source to the wrong behavior and confirm exactly the new test
  fails, then restore and confirm a clean diff.

### CON-009 — Structure is a contract

- `tests/python/<pkg>/test_<module>.py` mirrors `<pkg>/<module>.py`.
- `pathlib.Path` for every path operation; `os.path` string surgery is the
  legacy form. Resolve paths relative to `Path(__file__).resolve().parent`, not
  the caller's working directory.
- Every user-facing entry point answers `--help` in under 15 lines and exits 0
  *before* reading config or state — enumerated by `tests/bats/help_coverage.bats`.
- Exit codes: `0` success, `2` usage error, `1` failure. An empty result never
  exits 0 silently.

### CON-010 — Comments earn their place

- Docstring every public module, class, and function: what it is for and what it
  guarantees, not a restatement of the body.
- Comment the constraint, the rejected alternative, and the non-obvious
  ordering — the things the code cannot say.
- Delete commented-out code.

### CON-011 — Dependencies are liabilities

- Declare bounded ranges in `pyproject.toml` (`requests>=2.31,<3.0`); resolve
  them into `uv.lock`.
- Applications and services commit the lockfile and install from it —
  `uv sync --frozen` in CI, which fails on drift rather than silently
  re-resolving. Published libraries do **not** pin transitively; ranges only, so
  consumers can resolve.
- Refresh deliberately (`uv lock --upgrade`) on a schedule; let Renovate or
  Dependabot open the minor/patch and security PRs.
- Audit the lockfile for known CVEs (`pip-audit`) in CI, not at release.
- Before adopting anything: commits within six months, issues being triaged,
  ships `py.typed`, a small transitive tree, and a permissive license
  (MIT/Apache-2.0/BSD). Fail any one and the standard library answer wins.
- Secrets come from the environment. Never a literal, never a default value.

### CON-012 — Delete before you add

- Removing a feature removes its config keys, fixtures, docs, and tests in the
  same change.
- `ruff` flags the unused import; nothing flags the superseded config key or the
  orphaned fixture. Those are yours.

### CON-013 — No arbitrary execution

- `ast.literal_eval`, never `eval`/`exec`. A dict lookup beats both.
- `json` or a Pydantic model, never `pickle`/`marshal`/`dill` — unpickling
  builds arbitrary objects, so it is remote code execution with extra steps.
- `yaml.safe_load`. `yaml.load` without `Loader=SafeLoader` constructs Python
  objects from `!!python/object` tags.
- `subprocess.run([prog, *args])`. Never `shell=True`, `os.system`, or
  `os.popen`; pass argv and the metacharacters stay data.
- The SQL statement is a constant and the values are bound:

```python
# wrong — the value is compiled into the statement
cur.execute(f"SELECT * FROM t WHERE name = {name}")

# right — constant statement, bound parameter
cur.execute("SELECT * FROM t WHERE name = ?", (name,))
```

## Definition of done

- [ ] `ruff check` and `ruff format --check` pass on the changed files.
- [ ] `pyright` reports no new errors; every new public function is annotated.
- [ ] `pytest` passes, and the new test was observed failing before the fix.
- [ ] `constitution_check.py <files>` reports no `error`-tier violation.
- [ ] No file, class, or function crossed a ceiling without being split.
- [ ] No structured payload was added as a literal without an exemption comment
      carrying a reason.
- [ ] Every external input is parsed into a declared model at the boundary.
- [ ] Every acquired resource is released by a context manager.
- [ ] New dependencies are range-declared, locked, audited, and justified.
- [ ] Everything this change obsoletes is deleted in this change.
