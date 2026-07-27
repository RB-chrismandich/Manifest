# Decision Record — Feature 522 (APM deploy-pipeline migration)

**Spike run**: 2026-07-27 · **Tool under test**: `apm` (Microsoft Agent Package
Manager) **v0.26.0** · **Verdict**: 🚦 **NO-GO as measured** — two blocking
cells, each with a named unblocking action. Threat controls were populated
earlier by T050 (required before the spike could publish); every other section
below is this run's output.

## Decision

**NO-GO as measured.** Per T006, *"not measured is a NO-GO for that cell, not a
deferral."* Two cells fail. **This is not a recommendation to abandon the
feature** — the positive results are strong and specific:

- all three primitive types (skill / agent / hook) deploy at user scope;
- re-install is **byte-identical** (idempotent);
- rename genuinely **removes** the stale file — the ownership manifest, which is
  the central reason to adopt apm at all, works;
- the symlink fan-out **survives**, which was the risk most likely to kill T013.

**Blocking, in priority order:**

1. **Cell (b) — published package installed by name — was never measured.** No
   registry access was provisioned; this is the schedule risk SC-009 already
   boxed. It is also entangled with blocker 2 (below), so it must be measured
   first.
2. **Hand-edit retention contradicts the spec's own premise.** `spec.md:36`
   justifies apm partly because it *"retains user-edited files rather than
   overwriting them"*. Measured: it **overwrites them silently**. Decide whether
   deployed files are simply build outputs (hand-edits unsupported, FR-034
   rewritten) or whether a Manifest-side guard is required.
3. **Antigravity receives nothing at user scope** (cell c: 0 files). One of the
   five harnesses is unserved; decide whether that is acceptable or blocking.

Nothing below the Phase 0 checkpoint starts until 1 and 2 are closed.

### T001 — pinned install and trust surface (FR-029, E8)

| | |
|---|---|
| Resolved version | `Agent Package Manager (APM) CLI version 0.26.0` (self-reported) |
| Install method | PyPI wheel `apm_cli-0.26.0-py3-none-any.whl`, isolated venv |
| sha256, verified against the PyPI digest **before** install | `76290c42a9f9412e3ae8ea98d20acbdfbf4bee6dc32e951f616feab9bc82e7ad` |
| sdist sha256 (recorded, unused) | `24e6e4d346fb1d2ecbed05bb4205c3d99b284619344daf4007913985af488afb` |

1. **PyPI provenance does not tie the artifact to the source repo.** `apm-cli`
   0.26.0 ships `home_page: None`, empty `project_urls`, no author. The only
   Microsoft link is the MIT licence text. The binary's own version string is an
   assertion by the artifact, not provenance.
2. **`pip --require-hashes` is unusable as-is** — it demands every transitive
   dependency be hash-pinned.
3. **Dependency surface: 65 packages**, incl. `openai`, `gitpython`,
   `azure-ai-inference`, `llm`, `watchdog` — a large code-execution surface for
   a tool that writes into five home trees.
4. **`apm --help` alone creates `~/.apm/config.json`** (`{"default_client":
   "vscode"}`). The tool is not side-effect-free at any invocation; a repro must
   isolate `HOME` from the first command, not just the install.
5. Installing via a stdlib `venv` silently resolved to **system** site-packages
   and put 25 packages there. Detected and reverted. A repro MUST assert
   `site.getsitepackages()[0].startswith(sys.prefix)` *before* installing.

## Matrix results

All cells ran against an isolated `HOME`, certified by the T003 sentinel.

| Cell | Result |
|---|---|
| **(a)** local source, `--global` | ✅ skills **2/2**, agent **1/1**, hook **1/1** |
| **(b)** published package by name | ⛔ **NOT MEASURED** — no registry access |
| **(c)** `--target claude,cursor,antigravity` | ⚠️ claude 5 files, cursor 3, **antigravity 0** |
| **(d)** publish-free local loop | ✅ local path installs at user scope, no registry |
| **(i)** symlinked target | ✅ **symlink preserved** (`~/.cursor/skills -> ~/.claude/skills`) |
| **(ii)** installer-written mutation | ⚠️ key survived, but apm emits **no** installer-vs-human signal |
| re-install → byte-identical | ✅ **PASS** |
| rename → stale cleanup | ✅ old removed, new deployed |
| hand-edit → retention | ⛔ **OVERWRITTEN** |

### Per primitive type (an aggregate would have masked this)

Skills, agents and hooks all deploy. **Hooks land in `.claude/settings.json`** —
which is the file Claude Code actually reads at user scope (verified
independently 2026-07-26; `~/.claude/settings.local.json` is inert). apm targets
the correct file.

### ⛔ Hand-edit retention contradicts `spec.md:36`

- A canary appended to a deployed `SKILL.md` was **silently overwritten** on
  re-install (reproduced twice on a clean rig).
- **No user-edit warning at install time.** The only `[!]` lines concern target
  support and package collision ("1 skill replaced by a different package"),
  not local modification.
- **`apm audit` cannot see it either** — against the lockfile it reports *"No
  deployed files found in apm.lock.yaml"*: for a `_local` install the lockfile
  carries no deployed-file inventory, so there is nothing to diff.

This answers **E1** ("warning at install time, or only under `apm audit`?") with
a third option the spec did not anticipate: **neither**.

**Caveat, stated rather than glossed:** measured on a *local-path* install. The
empty deployed-file inventory suggests local installs may not be fully tracked,
so published installs — the decided model — could differ. That is cell (b),
which is unmeasured. The two blockers are entangled; (b) must be measured before
this finding is treated as final.

## Assumption cells

| Cell | FR | Downstream task | Verdict |
|---|---|---|---|
| (d) publish-free loop | FR-032 | T055 | ✅ **GO** |
| (i) symlink fan-out | FR-033 | T013 | ✅ **GO** — symlinks preserved |
| (ii) installer-vs-human | FR-034 | T051 | ⛔ **NO-GO** — apm cannot express it |
| (b) published install | FR-002 | the whole distribution model | ⛔ **NO-GO** — not measured |

## Threat controls

Concrete enforcing mechanism per threat (FR-018). Each is independent of
which registry model T005 ends up measuring (git-host or registry-protocol
server), and none trusts the `apm` binary's own supply-chain claims —
`apm`'s native capability is unmeasured before T005, so nothing here relies
on it.

- **Typosquatting** (installing a similarly-named but different package):
  enforced by **name-pinned install + independent hash verification**.
  `configs/claude/scripts/apm_install_verify.sh verify TREE --ref REF`
  recomputes the canonical content hash of whatever was actually fetched and
  accepts it only if it matches the single `result:"pass"` gate record for
  the exact `REF` requested. A typosquat package is different bytes under a
  similar name; it has no gate record for the ref the installer asked for,
  so it fails closed regardless of how convincing the package name is.
- **Dependency confusion** (a same-named package served from an
  unintended/attacker-controlled registry instead of the intended one):
  enforced by **single-registry pin + independent hash verification**. The
  install path is expected to resolve exactly one named registry/source, and
  `apm_install_verify.sh` re-hashes the fetched tree regardless of which
  registry actually served it. A confused resolution either violates the
  pin outright, or — if it doesn't — still has to produce bytes matching the
  hash recorded for the legitimate publish, which an unintended source
  cannot do without also compromising that publish's provenance.
- **Registry-account compromise** (an attacker publishes a malicious
  version under the legitimate maintainer's account): enforced because
  `configs/claude/scripts/apm_publish_gate.sh all` only records a
  `subject_sha256` for a tree that also passed `apm_publish_gate.sh
  provenance` (T049/FR-038) — a clean working tree at a tagged commit. A
  compromised registry account can push arbitrary bytes to the registry, but
  cannot retroactively produce a matching `result:"pass"` gate record for
  those bytes without also compromising the source repository and its tag.
  `apm_install_verify.sh` rejects the mismatch at install regardless of what
  the registry itself will serve.

## Control case

T006 requires a known-good control so operator error cannot masquerade as NO-GO.
The sentinel **mutates a real in-scope file** (`~/.claude/CLAUDE.md`), asserts
the rig detects it, restores it, and asserts the baseline returns. It refuses to
certify unless the control fires. Result: **control PASS**.

This was not theoretical. Sentinel **v1 produced a false NO-GO**: it flagged
`backups/`, `security/`, `sessions/` and `plugins/**/.in_use/<pid>` — all
written by the live Claude Code session running the spike, none by apm. v1 also
watched only `~/.claude`, so a real leak into `~/.apm` (finding T001.4) was
structurally invisible to it. Both defects were found by running the rig, and
both are exactly the failure mode this control exists to prevent.

## Evidence

### T003 sentinel — does `apm` honour `$HOME`? ✅ **PASS**

The single assumption the whole spike rests on. If apm resolved the OS home via
a syscall ignoring `$HOME`, every "isolated" result would be silently invalid
while reporting clean.

- **186,396 files** hashed across `~/.apm`, `~/.cache/apm` and all five
  assistant homes — **byte-identical** before/after a real, work-doing install
  (3 integrations, 5 files deployed into the isolated home).
- **No watched tree created or removed** — notably `~/.apm` did not appear.
- **Control case fired** (see above).

An earlier run wrapped `apm install --global`, which exits 1 ("no user-scope
`apm.yml`") and writes nothing — a sentinel over a no-op proves nothing. The
certifying run wraps an install that demonstrably deploys.

### Raw artifacts

Rig lives in the spike scratch dir (outside the repo, per the Phase 0 isolation
rule — T001–T006 modified nothing under `configs/`, `bootstrap*`, `.skillshare/`
or `tests/`):

- `sentinel.sh` — T003, with control case and churn exclusions
- `matrix.sh` — T005 cells
- `evidence/` — raw logs, hashes, before/after manifests, install transcripts
