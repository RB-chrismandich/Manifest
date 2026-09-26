# Knowledge Base

> Generated from the bundled seed registry plus XDG-owned `entries.jsonl` by `learning-capture sync-docs`.

## Antipattern

### ANTI-001: Unquoted variable expansion in shell commands

User-controlled values passed to bash -c, eval, or unquoted in command strings cause command injection (CWE-78).
Always quote variables; use arrays for command arguments; avoid bash -c with interpolated strings.

### ANTI-002: Insecure temporary file/directory creation

Using predictable temp paths or mkdir without mktemp enables symlink attacks (CWE-377). Always use mktemp -d with
templates; set umask 0077; use trap for cleanup.

### ANTI-003: Stale file-path references in pre-commit hooks

Local pre-commit hooks reference old directory paths after refactors, causing hooks to silently never match any files.
Update all path patterns in .pre-commit-config.yaml as part of every directory restructuring; add a CI check that
validates hook file patterns match existing paths.

### ANTI-004: Markdown table column style violations (MD060)

Tables use compact pipe style (no spaces around pipes in separator rows) which violates markdownlint MD060. Not auto-
fixable by --fix. Either add MD060: false to .markdownlintrc or reformat all table separator rows.

### ANTI-005: Documentation path drift after directory moves

After moving files to new directories, documentation references to old paths remain stale across multiple files.
Create a checklist or script that greps for old path prefixes after any directory restructuring commit.

### ANTI-006: Refactoring avoidance (linear accretion)

Features are bolted onto existing code without restructuring; functions and files grow linearly until no seam is left
to test or reuse. Endemic to AI-iterated code (90-100% occurrence in studied repos).

### ANTI-007: Context-induced monolith (return of the monolith)

As session context fills, new functionality lands in existing oversized files instead of properly scoped modules,
abandoning earlier modular decisions.

### ANTI-008: Cosmetic abstraction (single-impl interface, no isolation)

Interfaces/abstract classes with exactly one implementation that add no isolation, testability, or substitution
benefit — indirection that relocates complexity instead of hiding it.

### ANTI-009: Broken abstraction (interface bypassed by concrete references)

A well-defined interface exists but consumers reference the concrete type anyway (casts, direct construction, reaching
into internals), so the boundary no longer isolates anything.

### ANTI-010: Dead or orphan module (zero live callers)

Modules/functions with no active non-test caller. Often speculative code or leftovers after refactors; a module only
referenced by its own tests is dead code masquerading as live.

### ANTI-011: Near-duplicate function (context-loss duplication)

A utility is regenerated 100+ lines away or in another file because earlier context was lost, leaving near-identical
logic that will drift (one copy gets the fix, the other keeps the bug).

### ANTI-012: Excessive inline commenting substituting for readable code

Comments narrate every trivial line (a hallmark of AI generation) instead of the code being self-explanatory; they rot
immediately and bury the few comments that carry real constraints.

### ANTI-013: Phantom guards and over-specified edge cases

Defensive checks for impossible or already-excluded conditions clutter core logic (null-checking a value proven non-
null, re-validating internally produced data), adding noise without safety.

### ANTI-014: Vanilla style: no separation of concerns

Business logic, data access, and presentation interleaved in single functions with no service/layer boundaries, making
the code untestable and every change a cross-cutting edit.

### ANTI-015: Shallow test coverage (presence, not behavior)

Many tests, little depth: assertions only check that code runs or mocks were called, not outcomes; AI-generated tests
often mirror the implementation (circular validation) and miss semantic edge cases.

### ANTI-016: Unhandled async operation (un-awaited/uncaught)

Async work launched without awaiting or attaching error handling: rejections vanish, ordering becomes racy, and
failures surface later as unrelated crashes.

### ANTI-017: Orphan state (conditional write, unconditional read)

State initialized then written only on some paths but read without guards on all paths — or state that is never
consumed at all. Includes the stale-closure variant where async work mutates state after teardown.

### ANTI-018: Missing teardown for listeners, subscriptions, timers

Event listeners, subscriptions, sockets, or timers registered during setup with no corresponding cleanup on
destroy/unmount, causing leaks and stale-state mutations.

### ANTI-019: Shared-state race (non-atomic concurrent writes)

Two or more concurrent writers mutate shared state (file, global, cache, DB row) without locking/serialization: re-
entrant handlers, polling loops without cancellation, non-atomic read-modify-write file updates.

### ANTI-020: Collection boundary cases unhandled (empty/null/single)

Code that processes collections assumes a happy-path plural case and breaks on empty, null/missing, or single-item
inputs; zero is treated as falsy-absent.

### ANTI-021: Catch-log-return-undefined (swallowed error)

A catch block logs and falls through, so the caller receives undefined/None/zero-value with no failure signal and
crashes later or corrupts state. In web handlers, the global error middleware never fires.

### ANTI-022: Catch-and-discard without propagation or fallback

try/catch wraps a block purely to suppress failure — empty catch, catch returning a default silently, or catch
continuing a multi-step operation as if step N had succeeded.

### ANTI-023: Symmetric generic error messages

Every failure produces the same generic message ("Something went wrong", "Error: operation failed") regardless of
cause, making triage impossible while looking robust.

### ANTI-024: Missing input validation at function boundaries (CWE-20)

Functions consume external input (args, request bodies, env, file content) directly without null/type/range checks at
the boundary — the most common security-relevant flaw in LLM-generated code across languages.

### ANTI-025: Hardcoded secret in source (CWE-798)

API keys, passwords, JWT signing keys, or connection strings embedded as literals in source or committed
.env/.env.example files instead of loaded from the environment or a secrets manager.

### ANTI-026: Missing resource-level authorization (IDOR)

Routes check authentication but not ownership: predictable IDs are accepted and any logged-in user can read/mutate
another user's resource. 53% of critical vulns in AI-generated apps; near-invisible to SAST.

### ANTI-027: Weak cryptography or insecure randomness (CWE-327)

MD5/SHA-1 for password hashing, Math.random()/time-seeded values for tokens, or hand-rolled encryption instead of
vetted primitives and libraries.

### ANTI-028: Permissive CORS / missing HTTP security headers

Wildcard (*) CORS origins on authenticated endpoints and absent Content-Security-Policy, X-Content-Type-Options,
X-Frame-Options, or HSTS — the default shape of AI-generated web apps.

### ANTI-029: Sensitive data in logs or debug output

console.log/print statements left on production paths emitting request bodies, tokens, PII, or stack traces to user-
facing responses and log sinks; debug flags not gated by environment.

### ANTI-030: Hallucinated or unverified dependency (slopsquatting risk)

Depending on packages that don't exist on the registry (AI-invented names) or were never verified for maintenance/CVEs
— attackers register hallucinated names with malicious code.

### ANTI-031: Stale or vulnerable version pin

Pins reproduce versions that were current at model-training time but are now deprecated or carry patched CVEs,
silently re-introducing fixed vulnerabilities.

### ANTI-032: Environment-sensitive code without pinning or config validation

"Worked on my machine": implicit reliance on unpinned tool versions, ambient env vars, or absolute paths;
process.env/os.environ read throughout the code with no startup validation, failing silently elsewhere.

### ANTI-033: Security-control removal during refinement

Iterative "improvement" passes strip validation, auth checks, or error handling in pursuit of brevity or features —
the feedback-loop degradation that raises critical vulnerabilities 37.6% over five iterations.

### ANTI-034: Convention drift across sessions (pattern abandonment)

Naming styles, error-handling idioms, or architectural patterns established early are abandoned in later-generated
code; inter-session boundaries carry silent contract mismatches.

### ANTI-035: Literal prompt fixation (no architectural extrapolation)

The request is implemented word-for-word with no consideration of the surrounding architecture: duplicate mechanisms
get added where an existing subsystem should be extended, and implied requirements are ignored.

### ANTI-036: Bug deja vu (same error class recurring across sessions)

The same class of mistake reappears in session after session because nothing persists the lesson; each fix is local
and the pattern is never recorded.

## Config Insight

### CI-001: MD060 rule requires explicit decision

The MD060 (table-column-style) rule is enabled by default and triggers 902 violations across 48 files. Since --fix
cannot auto-fix this rule, either disable it in .markdownlintrc or reformat all tables. A decision should be made and
documented.

### CI-002: Local hook file patterns must be updated on directory moves

Pre-commit local hooks use files: regex patterns that are not validated against the actual file tree. After directory
restructuring, hooks can silently stop matching. Validate patterns after every rename.

## Pattern

_No entries yet._

## Tool Discovery

### TD-001: Use ruff instead of flake8+black+isort

Ruff is a single, fast Rust-based linter and formatter that replaces flake8, isort, pycodestyle, and several other
Python tools. Significantly faster and supports auto-fix for most rules.
