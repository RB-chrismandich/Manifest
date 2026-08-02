<!-- doc-type: reference -->
# Code Constitution — Node.js / TypeScript Annex

> The compiler settings, schema boundaries, module seams, and async contracts that make the
> universal articles checkable in TypeScript.

**Last Updated**: 2026-07-29
**Audience**: AI assistants and contributors writing Node.js / TypeScript
**Purpose**: Give the universal articles their TypeScript-specific ceilings, idioms, and gates

Universal articles: [code-constitution.md](../code-constitution.md).
Adjacent machine copy: `../../config/code_constitution.json` (`languages.node`).

## Toolchain

| Role | Tool | Rule |
|---|---|---|
| Manifest | `package.json` | Single source of scripts, `engines`, and `exports`; no second file restates a field it carries. |
| Packager | `npm` | `package-lock.json` is the only lockfile; CI installs with `npm ci`, never `npm install`. |
| Linter | `eslint` | Flat config only (`eslint.config.js`), extending `typescript-eslint` `strictTypeChecked` with `projectService: true` — without type-aware rules the lint is decorative. |
| Formatter | `prettier` | The only formatter. ESLint carries no formatting rules; a disagreement is resolved in `.prettierrc`. |
| Typechecker | `tsc` | `tsc --noEmit` is a gate, not advice. `strict: true` is the floor, not the target. |
| Tests | `vitest` | The only runner. Gates run `vitest run`; watch mode never appears in CI. |
| Audit | `npm audit` | Run against the committed lockfile. A finding is fixed, `overrides`-pinned with a stated reason, or the dependency is dropped. |
| Runtime | `node` (`engines.node`) | Declared in `engines`, matched by the CI matrix, and builtins imported with the `node:` prefix. |
| Boundary schema | `zod` or equivalent | One schema module per boundary; the TypeScript type is `z.infer`-ed from the schema, never declared beside it. |

The canonical settings live in `templates/scaffold/node/` — `tsconfig.json` (`strict`,
`noUncheckedIndexedAccess`, `noImplicitReturns`, `noUnusedLocals`, `isolatedModules`,
`verbatimModuleSyntax`), `eslint.config.js`, and `package.json.tmpl` (`"type": "module"`,
`engines.node >= 20`). Start from those rather than re-deriving them.

In this repository the `mirrors-eslint` pre-commit hook is pinned at v9.18.0 and excludes
`templates/`, `.Jules/`, and `.apm/skills/`; there is no root flat config, so a tracked `.ts`
or `.js` outside those paths must resolve to an `eslint.config.js` or the commit gate fails on
a missing config rather than on real findings. `docs/CODING_STANDARDS.md` has no Node section
yet — until it does, this table and `templates/scaffold/node/` are the authority.

## Size ceilings (CON-002)

| Unit | Ceiling | Split when |
|---|---|---|
| File (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`) | 400 lines | A second exported concern appears that no caller imports alongside the first. |
| Class | 200 lines | The fields divide into two groups no single method touches together. |
| Function | 50 lines | A named block inside it would read as a verb — extract it and call it. |
| Methods per class | 12 | The class has become a namespace; move a cohesive method group to its own module. |
| Parameters | 4 | The fifth argument arrives — take a typed options object instead. |
| Nesting depth | 4 | A guard clause, early `return`, or extracted predicate would flatten it. |
| Duplicate block | 8 lines | The third occurrence exists — extract and delete the other two (CON-003). |
| Payload literal | 8 lines | The literal crosses eight lines — see the extraction map below. |

Split along ESM module boundaries, not line counts: the transport layer (HTTP route, CLI
handler, worker entry) parses and validates, a service module holds the decision, and a
repository module owns I/O. A feature directory's `index.ts` re-exports only the names outside
callers use — `export *` turns the barrel into an import of the whole subtree, is the usual
source of require-cycle warnings, and hides dead exports from `noUnusedLocals`. A class at 200
lines with 12 methods is normally a namespace in disguise: extract the cohesive method group
into a module of plain exported functions, which ESM already scopes. A `.tsx` component counts
against the same 400 lines — extract a sub-component or a hook, never the JSX halfway line.

## Payload extraction map (CON-004)

| Payload | Lives in | Loaded by |
|---|---|---|
| SQL statement or migration | `data/sql/<name>.sql` | One query loader; values bound by the driver, never interpolated into the literal. |
| HTML, email, or report template | `templates/<name>.html` | One render function taking a typed context object. |
| Prompt text | `templates/prompts/<name>.md` | The same loader every call site imports. |
| Seed data, lookup table, locale/currency map | `data/<name>.json` | One loader that schema-parses on read and caches the parsed result. |
| Test fixture object or recorded response | `test/fixtures/<name>.json` | The suite's fixture helper, typed by the same schema production uses. |
| Generated fixture or golden output | `test/fixtures/<name>.json`, committed | Its regeneration script, named in `package.json` `scripts`; never hand-edited. |
| Large `as const` object literal | `data/<name>.json` | One loader; keep only the derived `type` in source. |

**Legitimately inline**: a template literal short enough to read at a glance (under the
eight-line payload ceiling); a `const` object of string tags whose keys *are* the type; a TSDoc
`@example`; a fixture whose whole value is sitting beside its assertion; and the single-line
SQL a query builder emits. A tagged template that only interpolates (a `sql` or `html` tag) is
still a payload once its literal part crosses the ceiling — extract the literal, keep the tag.

## Article annexes

### CON-002 — One reason to change

- An `index.ts` that only re-exports is a public-surface declaration, not a convenience; list
  the names explicitly so removing one is a compile error at every call site.
- Import types with `import type` (`verbatimModuleSyntax` makes this load-bearing) so a type-only
  edge never becomes a runtime module edge.
- Under `Node16` resolution, relative ESM imports carry the `.js` extension even from `.ts`
  sources; a missing extension is a runtime `ERR_MODULE_NOT_FOUND`, not a type error.

```ts
// wrong — the barrel drags the whole feature subtree into every importer and creates cycles
export * from "./order-service.js";
export * from "./order-repository.js";

// right — the barrel names the public surface; internals stay reachable only by path
export { createOrder, cancelOrder } from "./order-service.js";
export type { Order, OrderStatus } from "./order-types.js";
```

### CON-005 — Typed, validated boundaries

- `strict: true` plus `noUncheckedIndexedAccess` is the boundary enforcement: without the
  latter, `arr[i]` and `record[key]` lie about being defined.
- Parse external input — HTTP body, `process.env`, file contents, subprocess stdout, message
  payload — with a schema at the edge. Inside the boundary the inferred type is a guarantee.
- `unknown` is the honest type for unparsed input; `any` disables every check downstream and
  `as` is an assertion the compiler cannot verify. Both need an inline reason if used.
- Model closed sets as a string-literal union backed by an `as const` object, never bare string
  comparisons; model variants as a discriminated union so `switch` exhaustiveness is checkable.
- Non-null `!` is a claim about runtime state — replace it with a narrowing check or a parse.

```ts
// wrong — the cast is a promise the compiler cannot keep; a bad field surfaces frames later
const body = (await res.json()) as OrderRequest;

// right — one schema at the edge, the type inferred from it, the failure named at the boundary
const OrderRequest = z.object({ id: z.string().uuid(), qty: z.number().int().positive() });
type OrderRequest = z.infer<typeof OrderRequest>;
const body = OrderRequest.parse(await res.json());
```

### CON-006 — Extension by addition

- Key the registry on the string-literal union, and type it with `satisfies Record<Kind, …>` so
  a new union member that nobody registered is a compile error.
- End an exhaustive `switch` with a `default` that assigns the scrutinee to `never`; adding a
  variant then fails the typecheck instead of falling through at runtime.
- One implementation is not an interface. Export the concrete function; introduce the type on
  the third real caller.

```ts
// wrong — every new format edits this function
if (k === "csv") return csv(r);
else if (k === "json") return json(r);

// right — a new format adds a row; a missing one fails `tsc`
const RENDERERS = { csv, json, xml } as const satisfies Record<Format, Renderer>;
const render = (k: Format, r: Row): string => RENDERERS[k](r);
```

### CON-007 — Errors travel

- Every promise is awaited, returned, or explicitly routed. A floating promise loses its
  rejection; `@typescript-eslint/no-floating-promises` (in `strictTypeChecked`) is the gate, and
  `void somePromise` is only acceptable with a comment saying who handles the failure.
- Subclass `Error`, set `name`, and pass `{ cause: err }`. A rethrow that drops `cause` deletes
  the only stack that names the real failure.
- `catch (err)` is typed `unknown` — narrow with `instanceof` before reading `.message`; never
  assume the thrown value is an `Error`.
- `Promise.all` rejects on the first failure and abandons the rest; use `Promise.allSettled`
  when partial success is the intent, and report which entries failed.
- Cancellation is an `AbortSignal` threaded to `fetch`, timers, and streams — not a boolean flag
  the loop checks. Pair every `addEventListener`, `setInterval`, and watcher with its removal in
  the same module.

```ts
// wrong — the cause dies here and the caller dereferences `undefined` far from the failure
try { return await fetchOrder(id); } catch (err) { logger.error(err); return undefined; }

// right — narrow, contextual, causal
try { return await fetchOrder(id); }
catch (err) { throw new OrderFetchError(`order ${id}`, { cause: err }); }
```

### CON-008 — Tests first

- Tests are `vitest`, run as `vitest run`, and live at the path mirroring the source
  (`src/orders/pricing.ts` → `test/orders/pricing.test.ts`).
- Table-driven cases use `it.each` / `describe.each` over a `const cases` array typed by the
  function's own parameter type, so a signature change breaks the table at compile time.
- Assert rejections with `await expect(fn()).rejects.toThrow(OrderFetchError)` — a bare
  `expect(fn())` on an async function passes while the promise rejects unobserved.
- Use `vi.useFakeTimers()` for interval and timeout behavior; never `await sleep(…)` in a test.
- Vary the fixture: a table where every row shares a value proves the parameter is read, not
  that it is used.
- Prove the guard by mutating the source to the wrong behavior, watching exactly that test fail,
  restoring, and confirming a clean `git diff`.

### CON-009 — Structure is a contract

- File names are kebab-case; the default export, if any, matches the file name.
- A CLI entry point starts `#!/usr/bin/env node`, answers `--help` (usage, exit 0) before
  reading config or state, and writes diagnostics to `stderr` with `process.exitCode`, not
  `process.exit()` mid-stream.
- Public entry points are declared in `package.json` `exports`; a path importable only as a deep
  relative reach into `dist/` is not a supported surface.
- Match the surrounding module's shape — a service directory that already separates
  `*-service.ts` from `*-repository.ts` gets the same split for the new feature.

### CON-010 — Comments earn their place

- TSDoc every exported function, class, and type: what it is for and what it throws. The
  signature already states the parameter types — a `@param` that restates one is noise.
- Every `any`, `as`, `!`, `// @ts-expect-error`, and `eslint-disable` carries an inline reason on
  the same or preceding line; `// @ts-ignore` is never used (`@ts-expect-error` fails when the
  error disappears, which is the point).
- Explain non-obvious async ordering — why an `await` is sequential rather than batched, why a
  listener is registered before the handshake.

### CON-011 — Dependencies are liabilities

- Check `node:` builtins first (`node:fs/promises`, `node:crypto`, `node:test`, global `fetch`,
  `structuredClone`) before adding a package; most micro-dependencies are now stdlib.
- Evaluate on: bundled types (not a `@types/*` afterthought), ESM support, transitive count,
  release activity, licence. Record the reason in the PR that adds it.
- `dependencies` are what the published surface needs at runtime; everything else is
  `devDependencies`. A test helper in `dependencies` ships to every consumer.
- Declare bounded ranges in `package.json`, commit `package-lock.json` for applications, and do
  not commit it for published libraries. `engines.node` states the supported floor and CI runs it.
- Run `npm audit` against the lockfile; pin a transitive fix with `overrides` and a comment
  naming the advisory. Secrets come from `process.env`, validated by the same schema layer as any
  other external input — never a literal, never a default value.

### CON-012 — Delete before you add

- Removing an export means removing its barrel re-export, its `exports` entry, its test, and its
  fixture in the same change.
- `noUnusedLocals`, `noUnusedParameters`, and `@typescript-eslint/no-unused-vars` catch the
  file-local residue; unused *exports* are invisible to both — delete them when you delete the
  last caller, not later.
- Dropping a tool means dropping its `devDependency`, its config file, and its `package.json`
  script together. A leftover config file is read as live by the next contributor.

### CON-013 — No arbitrary execution

- Never `eval()` or `new Function()`. Both compile caller-supplied text; the
  checker flags them on sight because neither has a safe reading.
- `JSON.parse` for data. If the shape matters, parse then validate with a schema.
- `child_process.execFile`/`spawn` with an argv array, never `exec()` with an
  interpolated command string — `exec` runs `/bin/sh`.
- SQL is a parameterized query, never a template literal:

```ts
// wrong — the value is compiled into the statement
db.query(`SELECT * FROM t WHERE name = '${name}'`);

// right — constant statement, bound parameter
db.query("SELECT * FROM t WHERE name = $1", [name]);
```

## Definition of done

- [ ] `npm run check` passes end to end (`eslint`, `prettier --check`, `vitest run`).
- [ ] `tsc --noEmit` is clean under `strict` and `noUncheckedIndexedAccess`; no new `any`, `as`,
      `!`, or `@ts-expect-error` without an inline reason.
- [ ] Every external input in the diff (`await res.json()`, `JSON.parse(`, `process.env.`, file
      reads) passes through a schema `parse` at the boundary.
- [ ] No floating promise: `@typescript-eslint/no-floating-promises` reports nothing, and every
      cancellable operation accepts an `AbortSignal`.
- [ ] Each new or changed source file has a test at the mirroring `test/` path; the new assertion
      was watched failing, the source mutated to the wrong behavior, exactly that test failed.
- [ ] No changed file exceeds 400 lines, no function 50, no signature 4 parameters, no block
      nests deeper than 4.
- [ ] Every literal payload over 8 lines lives in `data/`, `templates/`, or `test/fixtures/` and
      is read by one loader.
- [ ] `npm audit` shows no unresolved high or critical finding; `package-lock.json` is committed
      (application) or intentionally absent (published library); `engines.node` matches CI.
- [ ] Obsoleted exports, barrel re-exports, `devDependencies`, and their config files are removed
      in this change, not a follow-up.
