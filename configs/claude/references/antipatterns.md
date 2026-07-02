# Proactive Coding Anti-Patterns (Guardrail Registry Reference)

> Read on demand BEFORE writing or refactoring code (spec 457). The live source
> of truth is `~/.claude/config/knowledge_base.yml` (guardrail-tagged entries,
> including `provenance: session-capture` additions made after this file was
> written) — consult it when checking programmatically; this reference renders
> the seeded set for reading. Human-readable summary: `docs/KNOWLEDGE_BASE.md`
> (regenerate via `learning_capture.sh sync-docs`).

## Iron Rules (apply while writing, always)

1. **Propagate error signals** — every catch rethrows, returns a typed
   error/fallback the caller must check, or routes to a central handler.
   Never log-and-fall-through.
2. **Validate at the boundary** — type/presence/range checks at entry points;
   pass only validated values inward; distinguish zero from missing.
3. **Secrets from the environment** — no credential literals in source, tests,
   or `.env.example`; fail fast at startup when required config is absent.
4. **Handle the async lifecycle** — await or explicitly route every async
   operation; pair every listener/subscription/timer with its teardown;
   serialize or atomize concurrent writes.
5. **Refactor before accreting** — extract the seam before adding to an
   already-long function/file; search for an existing helper before writing one.
6. **No speculative code** — no guards for unreachable states, no single-use
   abstractions, no dead modules "for later".
7. **Verify dependencies exist** — check the registry (existence, maintenance,
   advisories) before adding any package; new deps must install in CI.

## Iterative-Refinement Safety (FR-010)

When modifying existing code, **preserve every existing security control and
validation** (guard clauses, auth middleware, input checks, error handling)
unless the removal is intentional and stated in the change description.
Refinement passes measurably degrade security (~37.6% more critical
vulnerabilities over five iterations); diff-review your own "cleanups"
specifically for deleted guards. When applying a fix pattern (e.g., query
parameterization), apply it to ALL instances in the file, not only new code.

## Conflict Rule

If a prevention rule conflicts with an explicit user instruction (e.g., a quick
prototype with hardcoded values), the user's instruction wins — note the
deviation and its risk in your response; do not silently comply or refuse.

## Severity → Action

| Severity | Action |
|----------|--------|
| critical | Block merge; immediate remediation |
| high | Fix before next release (blocks verdict when tagged security/error-handling) |
| medium | Fix within the current work cycle |
| low | Maintenance cycle |
| info | Document; refactor when convenient |

## Architectural / Structural (`arch`)

### ANTI-006 — Refactoring avoidance (linear accretion)

**Severity**: medium

Features are bolted onto existing code without restructuring; functions and files grow linearly
until no seam is left to test or reuse. Endemic to AI-iterated code (90-100% occurrence in studied
repos).

**Detection cue**: Diffs that only ever add lines to the same function/file; functions growing past
~50 lines across successive changes with no extraction commits.

**Do this instead**: Before adding to a function or file that is already long, extract the seam
first (new function/module), then add the feature to the extracted unit.

### ANTI-007 — Context-induced monolith (return of the monolith)

**Severity**: medium

As session context fills, new functionality lands in existing oversized files instead of properly
scoped modules, abandoning earlier modular decisions.

**Detection cue**: One file accumulating unrelated responsibilities late in a session; imports
fanning out from a single module that keeps absorbing new features.

**Do this instead**: Re-check the module map before placing new code: new responsibility = new
module. If a file exceeds ~500 lines or mixes concerns, split before adding.

### ANTI-008 — Cosmetic abstraction (single-impl interface, no isolation)

**Severity**: info

Interfaces/abstract classes with exactly one implementation that add no isolation, testability, or
substitution benefit — indirection that relocates complexity instead of hiding it.

**Detection cue**: Interface + sole concrete class pairs where deleting the interface changes no
behavior; factory-of-factory layers; wrappers that only delegate.

**Do this instead**: Introduce an abstraction only when a second implementation, a test seam, or a
module boundary demands it; otherwise use the concrete type directly.

### ANTI-009 — Broken abstraction (interface bypassed by concrete references)

**Severity**: medium

A well-defined interface exists but consumers reference the concrete type anyway (casts, direct
construction, reaching into internals), so the boundary no longer isolates anything.

**Detection cue**: Downcasts or instanceof/type-assertions on interface values; callers importing
the implementation module although an interface module exists.

**Do this instead**: Consume the boundary type everywhere; if a caller needs implementation details,
widen the interface deliberately or remove it — never bypass it.

### ANTI-010 — Dead or orphan module (zero live callers)

**Severity**: medium

Modules/functions with no active non-test caller. Often speculative code or leftovers after
refactors; a module only referenced by its own tests is dead code masquerading as live.

**Detection cue**: Exports never imported elsewhere; functions whose return value no caller
consumes; linter unused-symbol findings suppressed instead of resolved.

**Do this instead**: Delete unused code rather than keeping it "for later" — version control
preserves it. A module kept alive only by its tests should be removed with its tests.

### ANTI-011 — Near-duplicate function (context-loss duplication)

**Severity**: low

A utility is regenerated 100+ lines away or in another file because earlier context was lost,
leaving near-identical logic that will drift (one copy gets the fix, the other keeps the bug).

**Detection cue**: Blocks of 10+ similar lines appearing more than once; two helpers with near-
identical names/signatures (parseX/extractX) in one codebase.

**Do this instead**: Search for an existing helper before writing one (grep by domain noun/verb). If
a near-duplicate exists, consolidate and reuse instead of adding a sibling.

### ANTI-012 — Excessive inline commenting substituting for readable code

**Severity**: low

Comments narrate every trivial line (a hallmark of AI generation) instead of the code being self-
explanatory; they rot immediately and bury the few comments that carry real constraints.

**Detection cue**: Comment-per-line ratios near 1:1; comments restating the next statement
("increment counter"); narration of obvious control flow.

**Do this instead**: Comment only what code cannot express: invariants, constraints, and non-obvious
why. Rename/restructure instead of narrating what or how.

### ANTI-013 — Phantom guards and over-specified edge cases

**Severity**: info

Defensive checks for impossible or already-excluded conditions clutter core logic (null-checking a
value proven non-null, re-validating internally produced data), adding noise without safety.

**Detection cue**: Branches that no input can reach; repeated validation of the same value down a
call chain; guards on constants or freshly constructed objects.

**Do this instead**: Validate at the boundary once, then trust internal invariants. Add a guard only
for a reachable state you can name in a test.

### ANTI-014 — Vanilla style: no separation of concerns

**Severity**: medium

Business logic, data access, and presentation interleaved in single functions with no service/layer
boundaries, making the code untestable and every change a cross-cutting edit.

**Detection cue**: Handlers that parse input, query storage, compute, and format output inline;
SQL/HTTP calls inside rendering or CLI-argument code.

**Do this instead**: Keep I/O at the edges and logic in the middle: parse/validate at entry, compute
in pure functions, perform storage/network in dedicated modules.

### ANTI-015 — Shallow test coverage (presence, not behavior)

**Severity**: medium

Many tests, little depth: assertions only check that code runs or mocks were called, not outcomes;
AI-generated tests often mirror the implementation (circular validation) and miss semantic edge
cases.

**Detection cue**: Tests without outcome assertions (no expected values); no failure-path tests;
suites that pass unchanged when the core logic is inverted.

**Do this instead**: Every test asserts a specific observable outcome, including at least one
failure/edge path per behavior; write the assertion from the spec, not from the implementation.

## Async & State Management (`async-state`)

### ANTI-016 — Unhandled async operation (un-awaited/uncaught)

**Severity**: high

Async work launched without awaiting or attaching error handling: rejections vanish, ordering
becomes racy, and failures surface later as unrelated crashes.

**Detection cues**:

- `bash`: background jobs (&) never waited; pipelines where failures are ignored
- `go`: goroutine writing results with no errgroup/channel consumption
- `python`: asyncio.create_task without done-callback; coroutine never awaited warning
- `typescript`: floating promises (no await/.catch); async fn called in sync context

**Do this instead**: Every async operation is awaited or explicitly detached with an error route:
attach .catch/try-await, consume task results, and wait/reap background jobs.

### ANTI-017 — Orphan state (conditional write, unconditional read)

**Severity**: medium

State initialized then written only on some paths but read without guards on all paths — or state
that is never consumed at all. Includes the stale-closure variant where async work mutates state
after teardown.

**Detection cue**: Variables assigned inside if/try branches and dereferenced outside them; state
fields with writers but no readers; setState after unmount/cancel.

**Do this instead**: Make every state variable total: initialize with a valid value, or make all
readers handle the unset case; delete state that nothing reads.

### ANTI-018 — Missing teardown for listeners, subscriptions, timers

**Severity**: medium

Event listeners, subscriptions, sockets, or timers registered during setup with no corresponding
cleanup on destroy/unmount, causing leaks and stale-state mutations.

**Detection cues**:

- `go`: time.Ticker never Stop()ed; contexts without cancel
- `python`: signal/loop callbacks registered without remove in close/aexit
- `typescript`: addEventListener/subscribe/setInterval in mount hooks without cleanup return

**Do this instead**: Pair every registration with its teardown in the same change: cleanup function,
defer/finally, or destructor — written before the feature logic.

### ANTI-019 — Shared-state race (non-atomic concurrent writes)

**Severity**: high

Two or more concurrent writers mutate shared state (file, global, cache, DB row) without
locking/serialization: re-entrant handlers, polling loops without cancellation, non-atomic read-
modify-write file updates.

**Detection cue**: Read-modify-write of a shared file/variable without lock or rename-into-place;
handlers that can re-fire before the prior invocation completes; check-then-act on shared resources.

**Do this instead**: Serialize writers (lock, queue, single-writer) or make writes atomic (write-
temp-then-rename, compare-and-swap); add cancellation tokens to loops that can overlap.

### ANTI-020 — Collection boundary cases unhandled (empty/null/single)

**Severity**: medium

Code that processes collections assumes a happy-path plural case and breaks on empty, null/missing,
or single-item inputs; zero is treated as falsy-absent.

**Detection cue**: Indexing [0] without length checks; reduce/aggregate without initial value; `if
value:` treating 0/empty as missing; division by len(items).

**Do this instead**: Trace every collection path for empty, single, and absent inputs before
shipping; distinguish "zero" from "missing" explicitly (is None / undefined checks, not truthiness).

## Error Handling (`error-handling`)

### ANTI-021 — Catch-log-return-undefined (swallowed error)

**Severity**: high

A catch block logs and falls through, so the caller receives undefined/None/zero-value with no
failure signal and crashes later or corrupts state. In web handlers, the global error middleware
never fires.

**Detection cues**:

- `bash`: cmd || echo 'warn' continuing; errors masked by local var=$(cmd)
- `go`: if err != nil { log.Println(err) } without return err
- `python`: except Exception: logger.error(...) then falling off the function end
- `typescript`: catch (e) { console.error(e) } with no rethrow/return in a value-returning fn

**Do this instead**: Every catch propagates a usable signal: rethrow, return a typed error/fallback
the caller must check, or route to a central handler that notifies the caller. Never log-and-fall-
through.

### ANTI-022 — Catch-and-discard without propagation or fallback

**Severity**: high

try/catch wraps a block purely to suppress failure — empty catch, catch returning a default
silently, or catch continuing a multi-step operation as if step N had succeeded.

**Detection cue**: Empty catch/except-pass blocks; catch returning [] / {} / null silently in data-
loading code; loops that continue past per-item failures uncounted.

**Do this instead**: Suppress an error only with a named reason: comment the invariant, count and
report skipped items, and make silent defaults impossible on write paths.

### ANTI-023 — Symmetric generic error messages

**Severity**: low

Every failure produces the same generic message ("Something went wrong", "Error: operation failed")
regardless of cause, making triage impossible while looking robust.

**Detection cue**: Multiple catch sites emitting identical strings; error text without the failing
input, path, or operation; rethrows that drop the original cause.

**Do this instead**: Error messages name the operation, the offending input/path, and preserve the
cause chain; user-facing text may be generic only when the full detail is logged with correlation.

### ANTI-024 — Missing input validation at function boundaries (CWE-20)

**Severity**: high

Functions consume external input (args, request bodies, env, file content) directly without
null/type/range checks at the boundary — the most common security-relevant flaw in LLM-generated
code across languages.

**Detection cues**:

- `bash`: Positional args ($1, $2) assigned and used with no arg-count/usage check or
- format/existence validation — a set -u unbound-variable crash is a symptom of missing
- validation, not a substitute for it; quoting alone is not validation.
- `general`: Request/CLI/env values used without schema or presence checks; parsing without
- try/error paths; validation deep in the stack instead of at entry.

**Do this instead**: Validate at the entry boundary (type, presence, range, size), reject early with
specific errors (usage message for CLIs), and pass only validated, typed values inward.

## Security (`security`)

### ANTI-001 — Unquoted variable expansion in shell commands

**Severity**: critical

User-controlled values passed to bash -c, eval, or unquoted in command strings cause command
injection (CWE-78). Always quote variables; use arrays for command arguments; avoid bash -c with
interpolated strings.

**Detection cues**:

- `bash`: unquoted $var in commands; bash -c/eval with interpolated strings
- `go`: exec.Command("sh", "-c", input); fmt.Sprintf into SQL
- `python`: subprocess(shell=True) or os.system with f-string user input
- `typescript`: child_process exec with template literals; SQL built by string concat

**Do this instead**: Never interpolate untrusted values into commands or queries: quote all shell
expansions, pass argv arrays (no shell=True / -c), and use parameterized queries or prepared
statements for SQL.

### ANTI-002 — Insecure temporary file/directory creation

**Severity**: high

Using predictable temp paths or mkdir without mktemp enables symlink attacks (CWE-377). Always use
mktemp -d with templates; set umask 0077; use trap for cleanup.

**Detection cues**:

- `bash`: hardcoded /tmp/<name>; mkdir under /tmp without mktemp; no trap cleanup
- `python`: open()/os.mkdir on literal /tmp paths instead of the tempfile module

**Do this instead**: Create temp files/dirs with mktemp (or the language's tempfile API), set a
restrictive umask, and register cleanup (trap/finally) so paths are unpredictable and never leak.

### ANTI-025 — Hardcoded secret in source (CWE-798)

**Severity**: critical

API keys, passwords, JWT signing keys, or connection strings embedded as literals in source or
committed .env/.env.example files instead of loaded from the environment or a secrets manager.

**Detection cue**: String literals matching key/token/password patterns; base64 blobs assigned to
auth config; realistic values in .env.example; secrets in test fixtures.

**Do this instead**: Load credentials from environment/secret stores at startup with fail-fast
validation; commit only placeholder .env.example values; scan diffs with a secrets detector before
push.

### ANTI-026 — Missing resource-level authorization (IDOR)

**Severity**: critical

Routes check authentication but not ownership: predictable IDs are accepted and any logged-in user
can read/mutate another user's resource. 53% of critical vulns in AI-generated apps; near-invisible
to SAST.

**Detection cue**: Handlers fetching by request-supplied ID with no owner/tenant predicate;
authorization only in the client; JWT validated for signature but claims never checked against the
resource.

**Do this instead**: Authorize at the resource level on the server: every fetch/mutation filters by
the authenticated principal (owner/tenant scope), and JWTs are validated for signature, expiry,
issuer, and algorithm.

### ANTI-027 — Weak cryptography or insecure randomness (CWE-327)

**Severity**: high

MD5/SHA-1 for password hashing, Math.random()/time-seeded values for tokens, or hand-rolled
encryption instead of vetted primitives and libraries.

**Detection cues**:

- `go`: math/rand for tokens instead of crypto/rand
- `python`: random module for secrets instead of the secrets module; hashlib.md5 for auth
- `typescript`: Math.random()/Date.now() for tokens; createHash('md5') for passwords

**Do this instead**: Passwords use Argon2/bcrypt/PBKDF2; tokens use the platform CSPRNG; encryption
uses established libraries with modern defaults — never custom constructions.

### ANTI-028 — Permissive CORS / missing HTTP security headers

**Severity**: high

Wildcard (*) CORS origins on authenticated endpoints and absent Content-Security-Policy, X-Content-
Type-Options, X-Frame-Options, or HSTS — the default shape of AI-generated web apps.

**Detection cue**: Access-Control-Allow-Origin: * combined with credentials; no security-header
middleware registered; CSP absent on HTML-serving routes.

**Do this instead**: Enumerate allowed origins explicitly (never * with credentials) and register
the standard security-header set on every HTML/API surface at app setup.

### ANTI-029 — Sensitive data in logs or debug output

**Severity**: high

console.log/print statements left on production paths emitting request bodies, tokens, PII, or stack
traces to user-facing responses and log sinks; debug flags not gated by environment.

**Detection cue**: Logging whole request/response objects; error handlers returning stack traces to
clients; DEBUG=true defaults; tokens/secrets interpolated into messages.

**Do this instead**: Log identifiers, not payloads: redact tokens/PII at the logger boundary, return
generic errors to clients while logging detail server-side, and gate debug output behind environment
checks.

## Dependency / Supply Chain (`dependency`)

### ANTI-030 — Hallucinated or unverified dependency (slopsquatting risk)

**Severity**: critical

Depending on packages that don't exist on the registry (AI-invented names) or were never verified
for maintenance/CVEs — attackers register hallucinated names with malicious code.

**Detection cue**: New manifest entries never installed in CI; package names close to popular ones;
imports that resolve to nothing; simple tasks pulling deep dep trees.

**Do this instead**: Verify every new dependency on its official registry (existence, maintenance,
advisories) before adding; prefer the standard library for small needs; new deps must install and
build in CI in the same change.

### ANTI-031 — Stale or vulnerable version pin

**Severity**: high

Pins reproduce versions that were current at model-training time but are now deprecated or carry
patched CVEs, silently re-introducing fixed vulnerabilities.

**Detection cue**: Newly added pins older than the package's latest major/minor by years; lockfiles
with advisories flagged by audit tooling; EOL runtimes in configs.

**Do this instead**: Resolve versions from the live registry at edit time, run the ecosystem's audit
tool on every dependency change, and record why any pin is held back.

### ANTI-032 — Environment-sensitive code without pinning or config validation

**Severity**: medium

"Worked on my machine": implicit reliance on unpinned tool versions, ambient env vars, or absolute
paths; process.env/os.environ read throughout the code with no startup validation, failing silently
elsewhere.

**Detection cue**: env vars read deep in the stack with fallback defaults; no engines/runtime pin;
paths outside the repo hardcoded; missing single startup config check.

**Do this instead**: Validate all required env/config at startup (fail fast, name the missing key),
pin runtimes and tools in manifests, and resolve paths relative to the project root.

## Iteration / Process (`iteration`)

### ANTI-033 — Security-control removal during refinement

**Severity**: critical

Iterative "improvement" passes strip validation, auth checks, or error handling in pursuit of
brevity or features — the feedback-loop degradation that raises critical vulnerabilities 37.6% over
five iterations.

**Detection cue**: Diffs deleting guard clauses, auth middleware, validation branches, or try/except
blocks while claiming refactor/cleanup; parameterization added to new queries while raw ones remain
in the same file.

**Do this instead**: When modifying existing code, preserve every security control and validation
unless the removal is intentional and stated in the change description; diff-review refinements
specifically for deleted guards.

### ANTI-034 — Convention drift across sessions (pattern abandonment)

**Severity**: low

Naming styles, error-handling idioms, or architectural patterns established early are abandoned in
later-generated code; inter-session boundaries carry silent contract mismatches.

**Detection cue**: camelCase and snake_case mixed in one module; repository/factory pattern used in
early files and dropped later; two modules exchanging values with incompatible assumptions about
shape/units.

**Do this instead**: Before writing, read the neighboring code and match its idioms exactly (naming,
errors, structure); at integration points, verify the consumed contract against the producer's
actual output.

### ANTI-035 — Literal prompt fixation (no architectural extrapolation)

**Severity**: info

The request is implemented word-for-word with no consideration of the surrounding architecture:
duplicate mechanisms get added where an existing subsystem should be extended, and implied
requirements are ignored.

**Detection cue**: New code re-implementing an existing subsystem's job; features that ignore
established config/registry mechanisms; requested behavior wired in isolation from its obvious call
sites.

**Do this instead**: Map the request onto the existing architecture first: extend the subsystem that
owns the concern, honor existing extension points, and surface implied requirements instead of
ignoring them.

### ANTI-036 — Bug deja vu (same error class recurring across sessions)

**Severity**: low

The same class of mistake reappears in session after session because nothing persists the lesson;
each fix is local and the pattern is never recorded.

**Detection cue**: Reviews/lint runs flagging an issue type already fixed in earlier commits;
repeated hotfixes with identical shape in different files.

**Do this instead**: On the second occurrence of any mistake class, capture it into this registry
(learning_capture.sh) with a prevention rule so future sessions are warned proactively; consult the
registry before related work.
