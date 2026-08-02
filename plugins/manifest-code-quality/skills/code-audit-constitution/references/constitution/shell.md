<!-- doc-type: reference -->
# Code Constitution — Bash / Shell Annex

> Binds the universal articles to this repo's shell contract: `set -euo pipefail`, `err()`, the `--help`
> gate, and the shellcheck / shfmt / bats toolchain.

**Last Updated**: 2026-07-29
**Audience**: AI assistants and contributors writing Bash / Shell
**Purpose**: Supply the shell ceilings, payload destinations, and boundary idioms the universal articles leave open

Universal articles: [code-constitution.md](../code-constitution.md).
Adjacent machine copy: `../../config/code_constitution.json` (`languages.shell`).

## Toolchain

| Role | Tool | Rule |
|---|---|---|
| Linter | `shellcheck` | `--severity=warning` blocks at commit and CI; `--severity=info` is edit-time advisory. Suppress inline with a reason (`# shellcheck disable=SC2086 — <why>`), never file-level. |
| Formatter | `shfmt` | The only formatter. Exact flags: `-i 4 -ci -sr -ln bash`. Do not hand-format what shfmt will rewrite. |
| Tests | `bats` | The only test runner. Tests live in `tests/bats/`; `.bats` files are excluded from shellcheck and shfmt (bats syntax), so their gate is the runner plus the assertion lint. |
| Manifest | none | Shell has no manifest. The shebang plus `set -euo pipefail` is the whole declaration, and macOS Bash 3.2 is the compatibility floor. |
| Packager | none | No packager. Dependencies are external binaries probed at runtime (CON-011), never vendored into the tree. |
| Typechecker | none | No typechecker. `set -u`, `${var:?}`, and validation at the entry point are the substitute (CON-005). |
| Audit | none | No dependency audit exists for shell; the audit surface is shellcheck's injection classes (SC2086, SC2046) and the array lint. |
| Array lint | `tests/lint/check_array_expansion.sh` | Blocking at commit and CI. Empty-array expansion uses `"${arr[@]+"${arr[@]}"}"` or carries an inline `# array-safe`. |
| Assertion lint | `tests/lint/check_bats_assertions.sh` | Blocking on `.bats`. A non-final bare `[[ ]]` silently passes under Bash 3.2. |
| Help gate | `tests/bats/help_coverage.bats` | Enumerates every `bundle-runtime/scripts/*.sh`; opting out requires `# help-coverage: exempt — <why>` under the shebang. |

## Size ceilings (CON-002)

| Unit | Ceiling | Split when |
|---|---|---|
| File | 600 lines | A second concern appears (parse *and* deploy, detect *and* mutate) — move one to a sourced library. |
| Function | 60 lines | The body needs a comment to announce its next phase; that phase is the new function. |
| Positional parameters | 5 | A sixth input arrives — switch to parsed flags or take a config-file path instead of another slot. |
| Nesting depth | 4 | A conditional wraps a loop wrapping a conditional; invert with an early `return`/`continue` guard. |
| Duplicated block | 8 lines | The same block reaches a third site (CON-003). |
| Inline payload literal | 12 lines | A heredoc or string exceeds it (CON-004). |
| Class / methods per class | 0 — not applicable | Shell has no classes. The YAML records `class_lines: 0` and `methods_per_class: 0`; no annex may invent a substitute. |

The seam is the sourced library: `legacy-setup.sh` is 399 lines because `legacy-setup/lib/` holds one concern per file
(`platform.sh` detection, `config.sh` argument parsing and services config, `auth.sh`, `deploy.sh`, `mcp.sh`), each
sourced by a path anchored to the script. Split argument parsing and usage away from the work they configure, and
split read-only detection away from anything that mutates the filesystem. An inline block long enough to need a
heading comment becomes a named function in the same file first; a function needed by a second entry point becomes
`lib/<concern>.sh`.

## Payload extraction map (CON-004)

| Payload | Lives in | Loaded by |
|---|---|---|
| YAML/JSON config emitted by a heredoc | `templates/<subject>.yml.tmpl`, or `bundle-runtime/config/<subject>.yml` when it is static | `envsubst < "$tmpl" > "$dest"` in one writer function |
| Lookup tables (`case` chains, parallel arrays, provider maps) | `bundle-runtime/config/*.yml` | a resolver, the way `tracker_registry.py` reads `tracker_providers.yml` |
| Embedded Python / awk / jq programs in a heredoc | their own `.py` / `.awk` / `.jq` file beside the script | invoked by path: `python3 "${BASH_SOURCE[0]%/*}/x.py"` |
| Test data (mock JSON/YAML, seeded trees) | `tests/fixtures/` | the bats test by path (`tests/fixtures/mock_config.yml`) |
| Long report or Markdown output templates | `templates/` | `envsubst`, or a `printf` format kept beside the data it renders |

The in-repo offender is `write_services_config()` in `legacy-setup/lib/config.sh`: a ~155-line YAML document inside a
single `cat > "$SERVICES_CONFIG" << EOF` heredoc. yamllint never sees it, it diffs as one blob, and the committed
`configs/` copy of the same file is vestigial as a result. The fix shape is a template file plus `envsubst` (or a
generator that emits it), leaving the function holding only the substitution and the write.

**Legitimately inline**: the `--help` heredoc (the CLI contract caps it at 15 lines), a one-line JSON probe body, a
`printf` format string, a single-expression `jq` filter, and a bats fixture whose adjacency to its assertion is the
point. The test is whether another tool would parse it: if yamllint, jq, or markdownlint should be reading it, it is
a file, not a literal.

## Article annexes

### CON-001 — Search before you write

- Shell has no import graph, so a forked helper is invisible. Grep the function name across
  `bundle-runtime/scripts/*.sh`, `legacy-setup/lib/*.sh`, and `tests/lint/*.sh` before defining one.
- Output helpers already exist: `err()` in `bundle-runtime/scripts/`, the `print_error()`/`print_step()` family in
  `legacy-setup/lib/common.sh`. A second one in a file that already sources them is a fork.
- Platform probes, timeout wrappers, and path resolution live in `legacy-setup/lib/platform.sh` and `common.sh`.
- A new verb for an existing dispatcher (`git_ops.sh`, `tracker_ops.sh`, `label_sync.sh`) is added to that script,
  not wrapped by a new one.

### CON-003 — Third time, centralize

- The third copy moves to `legacy-setup/lib/<concern>.sh` for the bootstrap chain, or a `*_lib.sh` beside its callers
  (`apm_domains_lib.sh` is the existing pattern).
- Source by a path anchored to the script, never to the caller's cwd:
  `source "${BASH_SOURCE[0]%/*}/lib/common.sh"`.
- A sourced library defines functions and constants only — no work at source time. It may omit `set -e` only with
  the rationale stated in the file (`docs/CODING_STANDARDS.md`).
- Delete the two older copies in the same commit; a survivor diverges before anyone notices it was left behind.

### CON-005 — Typed, validated boundaries

- Quote every expansion, including `"$@"`. Empty arrays under Bash 3.2 + `set -u` need `"${arr[@]+"${arr[@]}"}"`.
- Required inputs use `${var:?message}`; optional inputs use `${var:-default}`. An unset variable must never expand
  to nothing inside `rm`, `cd`, or a path join.
- Validate argv at the entry point before any work: reject unknown flags, confirm paths exist and are readable, and
  exit `2` for usage errors on new entry points.
- End option parsing with `--` before user-controlled operands (`grep -- "$pat"`, `rm -- "$path"`). Never `eval`,
  and never interpolate input into shell source.
- Commands crossing to another program are arrays, not strings: build `cmd=(prog --flag "$v")`, run `"${cmd[@]}"`.

```bash
# wrong — unset dir deletes the cwd tree, and the operand word-splits
rm -rf $dir/*
# right — :? aborts on unset or empty, quoting keeps one operand, -- ends flags
rm -rf -- "${dir:?dir is required}"/*
```

### CON-006 — Extension by addition

- A new provider, service, or platform is a row in `bundle-runtime/config/*.yml` read by a resolver — not another
  `case` arm. `tracker_providers.yml` plus `tracker_registry.py` is the shape to copy.
- A `case` or `elif` chain reaching its third arm becomes a lookup keyed on data.
- A parser keyed on a literal allow/deny list of keys makes every new key a code change, and a mis-added key can
  silently replace an existing one. Key on structure (indentation, prefix) instead.
- Do not add a flag with one call site for a future caller: every flag is a permanent contract that `--help`,
  `help_coverage.bats`, and the docs must carry.

### CON-007 — Errors travel

- `set -euo pipefail` heads every standalone script. Sourced `legacy-setup/lib/` files may omit `-e`, with the reason
  written in the file.
- Guard every `$()` that parses external input: `v="$(cmd)" || { err "..."; exit 1; }`. A bare assignment aborts the
  script with no message. Audit with `/manifest-code-quality:shell-audit-pipefail`.
- No function or sourced file ends on `[[ cond ]] && action`: a false guard returns non-zero and aborts the caller.
  Audit with `/manifest-code-quality:shell-audit-errexit`.
- Route error and warning output through `err() { echo "<script-name>: $*" >&2; }`, prefixed with the script's own
  name. `legacy-setup/lib/` keeps `print_error()`. Exempt: usage text, interactive prompts, separators, success/info.
- Pair setup with an `EXIT` trap (`trap 'rm -rf "$tmp"' EXIT`); `deploy_reconcile.sh` regenerates its `restore.sh`
  from one so a partial failure still leaves a rollback.
- A check that could not verify something reports "unverified" and returns non-zero — a skipped check is never a
  green pass.

### CON-008 — Tests first

- The test path mirrors the source: `bundle-runtime/scripts/<name>.sh` → `tests/bats/<name>.bats`.
- Never pipe a bats run. The pipeline reports the last command's status, so a failing suite reads as green.
- A non-final bare `[[ ]]` inside `@test` silently passes on macOS Bash 3.2. Chain `|| return 1`, or move the
  assertion last; `tests/lint/check_bats_assertions.sh` blocks the rest.
- Isolate ambient state: point the script at a `mktemp -d` `HOME`/`TARGET_DIR`. A pass against your real
  an existing assistant home proves only that your machine is already configured.
- Prove the guard by mutation: flip the source to the wrong command, confirm exactly the new test fails, restore,
  confirm `git diff` is clean.

```bash
# wrong — reports tail's exit 0; `not ok` lines scroll past as a pass
bats tests/bats/x.bats | tail -5
# right — status comes from bats itself
bats tests/bats/x.bats > "$out"; rc=$?; tail -5 "$out"; exit "$rc"
```

### CON-009 — Structure is a contract

- Entry points in `bundle-runtime/scripts/`, sourced libraries in a sibling `lib/`, tests in `tests/bats/`, lint
  gates in `tests/lint/`.
- `--help` answers before any config read, state lookup, or dependency probe: usage ≤15 lines, exit 0. Verify it
  with an empty `HOME` — a wrapper that forwards to the home runtime exits 0 on your machine and 1 in CI.
- A helper with no CLI surface declares `# help-coverage: exempt — <rationale>` directly under the shebang. A bare
  opt-out with no rationale is itself a test failure.
- Shebang `#!/usr/bin/env bash`; `.sh` entry points are executable, `.bats` files are deliberately not.

### CON-010 — Comments earn their place

- Open every script with a header block under the shebang: one-line purpose, `Usage:`, and the exit-code map.
  `check_array_expansion.sh` is the model — its `--help` prints that block back with `sed`.
- Every suppression states its reason on the same line: `# shellcheck disable=SC2086 — <why>`, `# array-safe`,
  `# assertion-safe`. A bare marker is a silent widening of the rule.
- Comment the constraint that makes a line look over-complicated — Bash 3.2, BSD vs GNU flags, a subshell that
  exists to contain a `cd`. Nothing else records it.
- Delete commented-out code and banner art; `shfmt` will not remove either, and neither survives a rename.

### CON-011 — Dependencies are liabilities

- A shell dependency is an external binary. Probe with `command -v` (never `which`) and fail with a message naming
  the tool and its install command.
- Never gate a runtime path on a build tool the script does not call: a launcher requiring `uv` breaks every
  minimal-`PATH` context (launchd, cron, hooks). Exercise it under `env -i PATH=/usr/bin:/bin`.
- Assume BSD userland by default: `sed -i` takes an argument on macOS, `mktemp` needs a template, and `awk` may be
  mawk (no `[[:space:]]`). Use the portable form or hand the work to Python.
- Prefer Bash builtins and coreutils to a new binary; `jq`/`yq` earn their place by parsing, not by convenience.
- Tool versions are pinned in `.pre-commit-config.yaml` and the CI workflow — a bump is a change to both.

### CON-012 — Delete before you add

- Deleting a script deletes, in the same commit, its `tests/bats/<name>.bats`, its help-coverage exemption, its
  pre-commit entry, and every caller reference.
- Unused variables are SC2034 findings, not history. Remove them rather than exporting them for a future caller.
- A retired flag is removed from the parser, `--help`, and the docs together; one that still parses but does
  nothing is worse than one that errors.

### CON-013 — No arbitrary execution

- No `eval` on a variable; use a `case` statement or an array.
- No `curl … | sh`. Download to a file, verify a checksum, then run it.
  `legacy-setup/lib/install.sh` carries six of these against upstream installers
  that publish no checksum — each is baselined, not blessed.
- Quote every expansion so a value cannot become a word: `"$var"`, `"${arr[@]}"`.

## Definition of done

- [ ] `shellcheck --severity=warning <file>` is clean, and every `# shellcheck disable=` carries a reason inline.
- [ ] `shfmt -i 4 -ci -sr -ln bash -d <file>` prints nothing.
- [ ] `tests/lint/check_array_expansion.sh <file>` exits 0, or the flagged line carries `# array-safe`.
- [ ] `tests/lint/check_bats_assertions.sh <file>.bats` exits 0 for every `.bats` file touched.
- [ ] `HOME=$(mktemp -d) <script> --help` exits 0 and prints ≤15 lines of usage, or the file declares
      `# help-coverage: exempt — <rationale>` under the shebang.
- [ ] `bats tests/bats/<name>.bats` was run unpiped and its own exit status read.
- [ ] Mutation check done: the source was flipped to the wrong behavior, exactly the new test failed, the source was
      restored, and `git diff` is clean.
- [ ] Every error and warning path calls `err()` (or `print_error()` in `legacy-setup/lib/`) and exits non-zero.
- [ ] No heredoc over 12 lines emits JSON/YAML/config; the payload lives under `bundle-runtime/config/`,
      `templates/`, or `tests/fixtures/`.
- [ ] Every external binary the change introduces is probed with `command -v` and named in the failure message.
