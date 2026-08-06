<!-- doc-type: reference -->
# Code Constitution — Go Annex

> How the universal articles land in Go: package seams, interfaces defined at the consumer, `%w` error
> chains, owned goroutines, and `go:embed` in place of raw-string payloads.

**Last Updated**: 2026-07-29
**Audience**: AI assistants and contributors writing Go
**Purpose**: Give the universal articles their Go-specific ceilings, idioms, and commands

Universal articles: [code-constitution.md](../code-constitution.md).
Adjacent machine copy: `../../config/code_constitution.json` (`languages.go`).
Post-hoc audit: `/manifest-code-quality:go-refactor` grades an existing tree and owns its own
report format; this annex governs the write.

## Toolchain

| Role | Tool | Rule |
|------|------|------|
| Manifest | `go.mod` | Single source of module path, Go version, and dependency requirements; edited by `go get` / `go mod tidy`, never by hand. |
| Lockfile | `go.sum` | Committed with `go.mod` in the same change; only Go commands write it. |
| Packager | `go` | The toolchain is the packager — `go build`, `go get`, `go mod`. No second dependency manager, no vendored fork of a dependency. |
| Linter | `golangci-lint` | v2 (pinned `v2.12.2` in `.pre-commit-config.yaml`). One `.golangci.yml` at the module root is the only lint config; v2 schema (`version: "2"`, `linters.settings`, `formatters`), not v1. |
| Formatter | `gofumpt` | The only formatter, a strict superset of `gofmt`. No hand formatting, no per-file exemption. |
| Vet | `go vet` | Runs on every package; a successful `go build` is not the gate. |
| Tests | `go test` | `-race` for anything that starts a goroutine; `-count=1` when the assertion depends on a fresh run. |
| Audit | `govulncheck` | Run against the module, not a dependency list — it reports only vulnerabilities reachable from your call graph. |

The Go gate in this repo is **dormant** (no tracked `.go` files); the `golangci-lint` pre-commit hook is
configured with `types_or: [go]` and fires the moment a `.go` file is staged. Adding Go means adding the config
it needs in the same change, not after the first red run. The bundle-local `/manifest-code-quality:project-scaffold` Go templates are the starting point, but their
`.golangci.yml` is still v1-shaped (`linters-settings`, `issues`, no `version` key) and its `Makefile` formats
with `gofmt`/`goimports`: migrate both to the v2 schema and `gofumpt` in the change that lands the first package.

## Size ceilings (CON-002)

| Unit | Ceiling | Split when |
|------|---------|------------|
| File (`.go`) | 500 lines | A second responsibility appears in the file — move it to a sibling file in the same package, or to a new package. |
| Type and its method set | 250 lines | The type has grown a second subject; the methods for that subject become their own type. |
| Function or method | 60 lines | A named step inside it can be described without "and"; extract that step. |
| Methods per type | 12 | The method set splits cleanly into two consumer-facing groups. |
| Parameters | 4 | Three or more parameters travel together; give them an options struct (`ctx` never counts toward this). |
| Nesting depth | 3 | Any `if` that wraps the rest of the body — invert it into a guard clause and return early. |
| Duplicated block | 8 lines | The same block reaches a third site — extract it and delete the other two (CON-003). |

The seams are package boundaries, not file boundaries: one package per responsibility, named for what it
provides (`store`, `tokenizer`), never `util`, `common`, `helpers`, or `base`. Split transport from domain from
persistence — a handler that parses a request, applies a rule, and writes a row is three packages wearing one
file. A type that crossed both the 250-line and 12-method ceilings is a package waiting to be extracted, with the
type as that package's subject. Generated files carry a `// Code generated ... DO NOT EDIT.` header, are exempt
from these ceilings, and are regenerated rather than edited.

## Payload extraction map (CON-004)

Threshold: a literal of 8 lines or more that parses as, or structurally resembles, JSON / YAML / SQL / HTML /
Markdown is a `C-DATA` finding. Backtick raw string literals are the Go-specific offender.

| Payload | Lives in | Loaded by |
|---------|----------|-----------|
| SQL statements | `data/queries/*.sql` | `//go:embed data/queries/*.sql` into one `embed.FS`; one query accessor. |
| HTML / text templates | `templates/*.tmpl` | `template.ParseFS(assets, "templates/*.tmpl")`, parsed once at package init. |
| JSON / YAML config defaults | `data/*.yaml` | `//go:embed` plus one `Decode` into a declared struct. |
| Large constant lookup maps | `data/<subject>.json` | One loader parsing into a typed `map[K]V` at package init. |
| Prompt / message payloads | `data/prompts/*.md` | `//go:embed`; the file is the reviewable artifact. |
| Golden output, test inputs | `testdata/` | `os.ReadFile` in the test, behind a `golden(t, name)` helper with an `-update` flag. |

`go:embed` cannot reach outside the embedding package's directory, cannot follow `..`, and skips files whose
names begin with `.` or `_` unless the pattern uses the `all:` prefix. Place payload directories **inside** the
package that embeds them, or expose one `assets` package whose only job is to publish the `embed.FS`.

**Legitimately inline**: format strings and single-statement SQL that fit on one line; struct tags; enum and
sentinel values; doc comments; the case table of a table-driven test, whose whole point is being adjacent to its
assertion; the `//go:embed` directive patterns themselves; and error message text.

## Article annexes

### CON-001 — Search before you write

- `go doc ./...` and `go doc <pkg> <Symbol>` before adding an exported identifier — the name may already exist
  one package over.
- Check the standard library first: `slices`, `maps`, `cmp`, `errors`, `log/slog`, `sync`, `net/http` cover most
  of what a new helper package would.
- Grep the module for the concept and the string literal, not only the symbol; a second `retry` loop is usually
  spelled differently from the first.
- An existing package that is 80% right gets a new function or an option, not a fork under a new name.

### CON-004 — Data is not code

- Any payload another tool can parse becomes a real file plus a `//go:embed` directive; the directive must sit
  immediately above the `var`, with no blank line between them.
- Embed into `[]byte` or `string` for one file, `embed.FS` for a set; parse it once, at package init or in one
  loader function, never per call site.
- Test fixtures live in `testdata/` — the Go toolchain already ignores that directory when building.

```go
// wrong: an unreviewable payload compiled in as a literal
const schema = `{"type":"object","properties":{ ...40 more lines... }}`

// right: a real file, diffed line by line and linted by JSON tooling
//go:embed data/schema.json
var schemaJSON []byte
```

### CON-005 — Typed, validated boundaries

- Accept interfaces, return structs: parameters name the behavior you need; returns stay concrete so callers
  keep the full type.
- Never `map[string]any` or `any` across a package boundary. Declare a struct, give it field tags, and let the
  decoder fail with a field name.
- Validate at the decode point: `json.Decoder` with `DisallowUnknownFields`, one `Validate() error` on the
  declared type, called once at the edge.
- Closed sets are named types with an exhaustive `switch` (the `exhaustive` linter), not bare strings.

```go
// wrong: untyped bag in, concrete dependency welded to the signature
func Process(m map[string]any) (*store.PostgresWriter, error)

// right: behavior accepted, concrete result returned
type Sink interface{ Write(context.Context, Record) error }

func Process(ctx context.Context, r Record, out Sink) (*Result, error)
```

### CON-006 — Extension by addition

- Interfaces are declared by the **consumer**, in the package that calls them, and are one or two methods wide.
  A producer package exporting a wide interface nobody asked for is the wrong direction.
- Do not define an interface with exactly one implementation to "allow mocking" — use the concrete type until a
  second implementation exists.
- The third `case` in a dispatch switch becomes a registry map keyed by the discriminator; new behavior is one
  registration.

```go
// wrong: a branch per case, so every feature edits this file
switch kind {
case "github": return newGitHub(cfg)
case "gitlab": return newGitLab(cfg)
}

// right: a row per case; a new provider registers itself and this file is untouched
var providers = map[string]func(Config) (Provider, error){}

func Register(name string, f func(Config) (Provider, error)) { providers[name] = f }
```

### CON-007 — Errors travel

- Wrap with `fmt.Errorf("<what failed> %s: %w", subject, err)` — one `%w`, context the caller cannot reconstruct,
  no "failed to" prefix duplicating the chain.
- Inspect with `errors.Is` / `errors.As`, never string matching. Export a sentinel (`var ErrNotFound = ...`) when
  callers only branch on identity; define an error type when they need a field off it.
- Never discard an error into `_`. `errcheck` is non-negotiable, including deferred `Close()` on a writable
  handle — capture it into the named return.
- `context.Context` is the first parameter of every function that does I/O or spawns work, is never stored in a
  struct, and its cancellation is actually honored (`select` on `ctx.Done()`, `http.NewRequestWithContext`).
- Every goroutine has one owner, a defined exit condition, and an observable finish (`sync.WaitGroup`, a closed
  channel, or `errgroup`). A `go` statement with no exit path is a leak, not a background task.
- `panic` does not cross a package boundary; recover only at a process edge, and re-raise as a wrapped error.

```go
// wrong: cause dropped, error discarded, goroutine with no exit
return errors.New("load failed")
data, _ := io.ReadAll(r)
go poll()

// right: cause wrapped, error propagated, goroutine owned by a context
return fmt.Errorf("load %s: %w", path, err)
data, err := io.ReadAll(r)
if err != nil {
    return fmt.Errorf("read body: %w", err)
}
go func() { defer close(done); poll(ctx) }()
```

### CON-008 — Tests first

- One table-driven test per behavior: a `[]struct` of named cases, each run under `t.Run(tc.name, ...)` so a
  failure names the case rather than a row index.
- Vary the table — identical or flat inputs make the assertion pass without exercising the branch.
- Inputs and golden files go in `testdata/`; regenerate them through an `-update` flag, and review the golden
  diff as part of the change.
- `go test -race ./...` is the default invocation for any package with concurrency; helpers call `t.Helper()`,
  cleanup uses `t.Cleanup`, and tests never call `os.Exit`.
- Parsers and decoders get a `Fuzz` target seeded from `testdata/`.
- A new guard is unproven until the source was mutated to the wrong behavior, exactly that test failed, and the
  source was restored with a clean `git diff`.

### CON-009 — Structure is a contract

- Package name equals directory name, lowercase, no underscores, and is not repeated in its identifiers
  (`store.New`, not `store.NewStore`).
- Everything not meant for outside consumption goes under `internal/`; the compiler enforces that boundary, so
  use it instead of documenting an intention.
- Binaries live in `cmd/<name>/main.go` and stay thin: flag parsing, wiring, one call into a package that is
  testable without the binary.
- `foo_test.go` sits beside `foo.go`. Tests of the public surface use `package foo_test` so the API is exercised
  as a caller sees it.
- Every user-facing binary answers `--help` (usage, flags, exit 0) before reading config or state, and routes
  errors to stderr through one helper, matching the repo's Bash `err()` contract.

### CON-010 — Comments earn their place

- A doc comment starts with the identifier it documents and is a complete sentence: `// Load reads ...`.
- Every exported identifier and every package is documented; a package doc longer than a few lines lives in
  `doc.go`.
- `//nolint:<linter>` carries `// <reason>` on the same line and names the specific linter; blanket file-level
  suppression is not permitted.
- Commented-out code is deleted. `// TODO` without an issue reference is deleted with it.

### CON-011 — Dependencies are liabilities

- Standard library first — `slices`, `maps`, `errors`, `log/slog`, `net/http`, `testing` remove most candidate
  dependencies outright.
- `go.mod` and `go.sum` are committed in the same change as the import that needed them; `go mod tidy` runs
  before commit and leaves both files unchanged.
- `govulncheck ./...` runs on the module; a finding is fixed by upgrading or by removing the reachable call, not
  by suppressing the report.
- No `replace` directive pointing at a local path in a committed `go.mod`, and no dependency added for a helper
  under thirty lines.
- Secrets come from the environment, never a `const`, never a default in a `flag.String` call.

### CON-012 — Delete before you add

- `go mod tidy` in the same change that drops the last import of a dependency.
- The `unused` linter output is a work item, not noise: delete the unexported symbol rather than referencing it
  from a test to keep it alive.
- Removing a feature removes its package, its `_test.go`, its `testdata/` payloads, its registry row, and its
  flag — grep the flag string before declaring the removal done.
- Build tags gating dead platforms go with the code they gated.

### CON-013 — No arbitrary execution

- `exec.Command(prog, args...)` with the program and its argv. Never
  `exec.Command("sh", "-c", cmd)` — that hands a shell your string.
- `database/sql` placeholders (`?` / `$1`), never `fmt.Sprintf` into a query.
- `encoding/gob` deserializes into arbitrary registered types; prefer
  `encoding/json` into a declared struct for anything crossing a trust boundary.
- `text/template` auto-escapes nothing — use `html/template` for HTML output.

```go
// wrong — a shell parses every metacharacter in name
exec.Command("sh", "-c", "grep "+name+" f.txt")

// right — argv, no shell
exec.Command("grep", name, "f.txt")
```

## Definition of done

- [ ] `gofumpt -l .` prints nothing.
- [ ] `golangci-lint run ./...` is clean, and every `//nolint` names a linter and states a reason.
- [ ] `go vet ./...` is clean.
- [ ] `go test -race -count=1 ./...` passes, and each new guard was watched failing against a mutated source and
      restored to a clean `git diff`.
- [ ] `govulncheck ./...` reports no findings reachable from this module.
- [ ] `go mod tidy` leaves `go.mod` and `go.sum` unchanged (`git status --porcelain go.mod go.sum` is empty).
- [ ] No raw string literal of 8+ lines holds JSON, SQL, HTML, or template text; those payloads sit under
      `data/`, `templates/`, or `testdata/` and are reached by `//go:embed`.
- [ ] Every exported identifier added has a doc comment beginning with its name; `go doc ./<pkg>` reads as
      intended.
- [ ] Every goroutine the change starts has a named owner and an exit path driven by context cancellation or a
      closed channel.
- [ ] Every error path either wraps with `%w` or states inline why the chain stops there; no error is discarded
      into `_`.
