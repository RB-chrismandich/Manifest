# Decision Record — Feature 522 (APM deploy-pipeline migration)

**Spike run**: 2026-07-27 · **Amended**: 2026-07-27 (cell (b) run) · **Tool
under test**: `apm` (Microsoft Agent Package Manager) **v0.26.0** ·
**Verdict**: 🚦 **GO, with FR-034 and spec.md:36 to be corrected** — cell (b)
is now measured and passes; the remaining blocker is a spec claim that is
factually wrong, not a tool capability that is missing. Threat controls were
populated earlier by T050 (required before the spike could publish); every
other section below is spike output.

## Decision

**GO.** Cell (b) — the one cell that was unmeasured, and the one the whole
distribution model rested on — now passes on the decided model. Measured
positives:

- all three primitive types (skill / agent / hook) deploy at user scope, from
  a **published package installed by name** as well as from local source;
- re-install is **byte-identical** (idempotent);
- rename genuinely **removes** the stale file — the ownership manifest, which is
  the central reason to adopt apm at all, works;
- the symlink fan-out **survives**, on both the local and the published path,
  which was the risk most likely to kill T013;
- the published install writes a **full deployed-file inventory with per-file
  SHA-256** into `apm.lock.yaml` — the gap that made the 2026-07-27 retention
  verdict provisional is closed.

**The earlier NO-GO rested on a false premise.** It recorded cell (b) as
blocked on "registry access". `apm install owner/repo` does not resolve a
registry — it resolves a **git host** (see *Distribution model* below). No
account provisioning was ever required, and SC-009's two-day box existed for a
latency that does not apply.

**Remaining blocker — one, and it is a spec defect, not a tool defect:**

1. **`spec.md:36` states a capability apm does not have.** It justifies apm
   partly because it *"retains user-edited files rather than overwriting
   them"*. Measured on **both** install modes: it **overwrites them**, and
   `apm audit` cannot report it because deployed-file content drift is not one
   of the four drift categories apm implements. The spec sentence must be
   corrected regardless of which policy is chosen; FR-034 and T052 are built on
   it and must follow. See *Hand-edit retention* below.

**Resolved, was blocking:**

2. **Antigravity receives nothing at user scope** (cell c: 0 files) —
   **accepted; the symlink fan-out is the intended delivery mechanism**
   (maintainer decision, 2026-07-27). The published-install transcript names
   what apm cannot serve: `antigravity (instructions, hooks)`. Those are
   precisely the two primitive classes Manifest **deliberately does not deploy
   to `~/.antigravity`**. `deploy_antigravity_configs()`
   (`bootstrap/lib/deploy.sh:961`) links exactly `config`, `skills` and
   `.plans` from `~/.claude`, and passes `"scripts prompts"` as an explicit
   exclusion list to `link_shared_assets`; the surrounding comment records the
   live probe behind it — `agy` reads its config from `~/.gemini/config`, never
   from `~/.antigravity`, so an instructions file placed there would never be
   read. There are no antigravity hooks either.

   So the 0-file result is not a shortfall: apm has nothing to write for
   antigravity that Manifest wants written, and the one thing Manifest *does*
   want there — skills — arrives by symlink, which cell (i) measured as
   surviving an APM install on both the local and published paths. **Coverage
   is four physical harness trees plus one by symlink, which is what it is
   today.** Nothing to build; this is a decision, not a task.

   *Constraint this creates:* if Manifest ever needs to deploy real
   instructions or hooks to antigravity, apm cannot do it at user scope and
   this decision must be revisited. Recorded so a future change meets the
   constraint deliberately rather than discovering it.

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
| **(b)** published package by name | ✅ skills **2/2**, agent **1/1**, hook **1/1** (private GitHub repo, installed by name) |
| **(c)** `--target claude,cursor,antigravity` | ⚠️ claude 5 files, cursor 3, **antigravity 0** — accepted, see *Decision* item 2: the unsupported primitives are ones Manifest never sends there, and skills reach antigravity by symlink |
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

#### ✅ Caveat resolved, finding sharpened (cell (b) run)

The caveat above is now discharged, and the middle bullet was **wrong about the
cause**. Re-measured on the published install, whose lockfile *does* carry a
full `deployed_files` list plus `deployed_file_hashes`:

- The canary is still **overwritten**. Retention does not exist on either
  install mode. `spec.md:36` is factually wrong.
- **apm does detect the modified file — and misreports why.** The line
  `[!] 1 skill replaced by a different package (last installed wins)` appears
  **only** when the deployed file has been hand-edited; a clean re-install of
  the same package does not emit it (verified by differential run). `--verbose`
  gives the detail:

  ```text
  [!] 1 skill replaced by a different package (last installed wins)
      +- .claude/skills/spike-alpha
         Skill 'spike-alpha' replaced -- previously from another package
  ```

  There is no other package. apm interprets *"bytes differ from what I
  deployed"* as *"another package owns this"* and asserts a cause that is
  false. This is worse than silence for an operator, who will go looking for a
  collision that does not exist. The earlier record read this line as unrelated
  target/collision noise; it is in fact the hand-edit signal, mislabelled.
- **`apm audit` still cannot see it, and this is by design, not misconfiguration.**
  Run from the project dir it reports *"No apm.lock.yaml found"* (it does not
  look at user scope); pointed explicitly at the user-scope lockfile
  (`apm audit --file ~/.apm/apm.lock.yaml`) with the canary in place it reports
  *"1 file(s) scanned -- no issues found"*. The authority is apm's own
  `drift.py` docstring, which enumerates every drift category it implements —
  **ref**, **orphan**, **config** (MCP servers only), **stale-file**.
  Deployed-file *content* drift is not among them. `apm audit --help` advertises
  "drift"; that word means the four categories above, not user edits.

**Consequence for T052.** T052 is written as *"if retention is silent at
install and surfaced only by a separate `apm audit`, wire that audit into the
deploy path."* Neither branch of that conditional holds: retention does not
happen, and `apm audit` has no channel to surface it. T052 must be re-scoped to
whatever Manifest decides to do instead, or closed with this evidence.

## Assumption cells

| Cell | FR | Downstream task | Verdict |
|---|---|---|---|
| (d) publish-free loop | FR-032 | T055 | ✅ **GO** |
| (i) symlink fan-out | FR-033 | T013 | ✅ **GO** — symlinks preserved |
| (ii) installer-vs-human | FR-034 | T051 | ⛔ **NO-GO** — apm cannot express it |
| (b) published install | FR-002 | the whole distribution model | ✅ **GO** — measured 2026-07-27, all three primitive types deploy |

## Distribution model — corrected

The 2026-07-27 record boxed cell (b) as *"no registry access provisioned"* and
SC-009 budgeted an extra working day for provisioning latency. **Both rest on a
premise that the tool's source refutes.** Verified by reading apm-cli 0.26.0
(the wheel, not the docs):

| Assumed | Actual |
|---|---|
| "install by name" resolves a package registry | `apm install owner/repo` builds a **git-host URL** — `install/package_resolution.py` → `dep_ref.to_github_url()`; hosts enumerated in `core/host_providers.py` (github.com, `*.ghe.com`, GitLab, Azure DevOps, self-hosted). The lockfile records `host: github.com` and a `resolved_commit`. |
| a registry account must be provisioned | Nothing to provision. A public repo needs no credential; a private one authenticates via `GITHUB_TOKEN`, `GITHUB_APM_PAT_<ORG>`, `gh auth token`, or `git credential fill` (`core/auth.py`). |
| the REST registry is the shipping path | `apm publish` is gated behind `require_package_registry_enabled()` → `apm experimental enable registries`, **off by default**, and its own docstring says it implements `docs/proposals/registry-api.md` — an unratified proposal. `base_url` comes from a self-hosted `registries:` block in `apm.yml`. There is no operating public APM registry. |

**Cell (b) was therefore measured against a git host**, which is what
`spec.md:49`'s "published packages … installed by name" resolves to in
practice. Subject: a private GitHub repo, `apm.yml` + `.apm/` at the repo root,
tagged `v1.0.0`, published only after `apm_publish_gate.sh all` recorded a
`result:"pass"` line (SC-011).

**Ref pinning works and matters.** `apm install -g owner/repo` resolves the
default branch and warns
`[!] 1 dependency unpinned … add #tag or #sha to prevent drift`;
`apm install -g 'owner/repo#v1.0.0'` records `resolved_ref: v1.0.0` alongside
`resolved_commit`, deploys identically, and drops the warning.

**This reshapes FR-018.** Its threat controls are written for registry-shaped
attacks — typosquatting, dependency confusion between registries,
registry-account compromise. The real channel is a git host, where the
equivalent threats are **repo transfer / org rename** (a name freed up and
re-registered by an attacker), **tag mutability** (a tag moved to new bytes
after publication), and **default-branch resolution** (the unpinned case above,
which is mutable by construction). The existing controls — pin the ref,
independently re-hash the fetched tree against a gate record for that exact ref
— remain sound and largely cover these, but the *stated threats* no longer
match the *actual channel* and must be rewritten to it.

## Threat controls

Concrete enforcing mechanism per threat (FR-018). Each is independent of
which registry model T005 ends up measuring (git-host or registry-protocol
server), and none trusts the `apm` binary's own supply-chain claims —
`apm`'s native capability is unmeasured before T005, so nothing here relies
on it.

> **Amended 2026-07-27 (cell (b)).** T005 has now measured the model: it is a
> **git host**, not a registry protocol (see *Distribution model — corrected*).
> The three threats below are **re-aimed at that channel**, per the amended
> FR-018. The **mechanisms are unchanged** — being source-agnostic is exactly
> why they survive the correction; they verify bytes against a recorded hash,
> which does not care what served them. The original registry-shaped names
> (typosquatting, dependency confusion, registry-account compromise) are
> preserved in each bullet rather than deleted, because these controls were
> T050 output that gated a real publish and the audit trail should show what
> changed and why. They become live again if the experimental REST registry is
> ever adopted.

- **Repo transfer / org-name reuse** *(was: typosquatting)* — on a git host an
  `owner/repo` shorthand is a **mutable name**: rename, delete or transfer the
  repo and the freed name can be re-registered by anyone, so a later install of
  the identical string resolves to someone else's content. Registries do not
  generally free a published name, which makes this strictly worse than the
  threat it replaces. Enforced by **ref-pinned install + independent hash
  verification**.
  `configs/claude/scripts/apm_install_verify.sh verify TREE --ref REF`
  recomputes the canonical content hash of whatever was actually fetched and
  accepts it only if it matches the single `result:"pass"` gate record for
  the exact `REF` requested. Content served under a re-registered name is
  different bytes; it has no gate record for the ref the installer asked for,
  so it fails closed regardless of how legitimate the name looks.
- **Tag mutability / default-branch resolution** *(was: dependency confusion)* —
  a git tag is a **movable pointer**, and an unpinned install resolves the
  default branch, which is mutable by construction. Both let bytes change
  underneath a ref that verified at publish time; neither requires the attacker
  to control a second source. Measured on the real channel: `apm install -g
  owner/repo` resolved `#main` with only a `[!] 1 dependency unpinned` warning,
  while `owner/repo#v1.0.0` recorded `resolved_ref` **and** `resolved_commit`.
  Enforced by **ref pinning + independent hash verification**: `apm_install_verify.sh`
  re-hashes the fetched tree regardless of what the ref currently points at, so
  a moved tag or an advanced branch fails the hash for the ref requested.
  Manifest pins, and prefers a commit SHA over a tag wherever the pin is
  machine-consumed — the SHA is the only ref on a git host that is immutable by
  construction rather than by convention.
- **Source-repository compromise** *(was: registry-account compromise)* — an
  attacker with push rights publishes malicious content under the legitimate
  maintainer's account. Enforced because
  `configs/claude/scripts/apm_publish_gate.sh all` only records a
  `subject_sha256` for a tree that also passed `apm_publish_gate.sh
  provenance` (T049/FR-038) — a clean working tree at a tagged commit. The
  attacker can push arbitrary bytes, but cannot retroactively produce a
  matching `result:"pass"` gate record for them.
  `apm_install_verify.sh` rejects the mismatch at install regardless of what
  the host will serve.

  **Residual risk, stated rather than glossed:** on a git host the source
  repository and the distribution channel are *the same asset*, where a
  registry model separates them. An attacker who compromises the repo has, by
  construction, also compromised the thing the gate record is derived from —
  so this control degrades to "the attacker must also forge a gate record in
  Manifest's own history", which is a real barrier but a narrower one than the
  registry framing implied. Accepted for now; revisit if signed tags or an
  independent attestation store become available.

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

**Sentinel v3 (cell (b) run) — re-certified, and one more false-NO-GO source
removed.** Re-run before trusting any cell (b) result, per the rule that a
premise true last week may be false now. It initially failed its own control
("baseline not reproducible after restore") — **not** rig instability, but
ambient churn from *other* live processes inside the watched trees:
`~/.gemini/antigravity-cli/brain/*/.git/objects/**` and
`~/.gemini/antigravity-cli/log/*.log` (a running Antigravity CLI), and
`~/.claude/plugins/**/__pycache__/*.pyc` (bytecode written on import — v2's
`cache` exclusion matched only `.claude/cache`, not `.claude/plugins/cache`).
All are content-addressed or derived **storage**, never apm's deploy surface,
so they are excluded by path in v3. Detection is not narrowed: the control
canary remains `~/.claude/CLAUDE.md`, which *is* the deploy surface, and the
rig still refuses to certify unless mutating it is detected.

Result after the fix: **control PASS**, then **94,243 files byte-identical**
before/after a real work-doing install, no watched tree created or removed.
This is the third distinct false-NO-GO this control has caught (v1 twice, v3
once) — which is the argument for keeping it in T008 as a per-run assertion
rather than a one-time certification.

### T005 cell (b) — published package installed by name ✅ **PASS**

Subject: `rb-chrismandich/apm-spike-522`, private GitHub repo, tagged `v1.0.0`,
gate record `subject_sha256:548a0e3a…` `result:"pass"` written **before** the
push (SC-011). Run against the v3-certified isolated `HOME`.

```text
$ apm install -g rb-chrismandich/apm-spike-522 --target claude
[i] Installing to user scope (~/.apm/)
[>] Resolving rb-chrismandich/apm-spike-522...
  [+] rb-chrismandich/apm-spike-522 #main @34e73f25
  |-- 1 agents integrated -> .claude/agents/
  |-- 1 hook(s) integrated -> .claude/settings.json
  |   PreToolUse: runs echo spike-hook (spike-hook.json)
  |-- 2 skill(s) integrated -> .claude/skills/
  [!] 1 dependency unpinned: rb-chrismandich/apm-spike-522 -- add #tag or #sha
[*] Installed 1 APM dependency in 2.8s.
exit=0   skills=2  agents=1  hook_in_settings=1
```

Per primitive type, because an aggregate would mask a hook failure:
**skills 2/2, agents 1/1, hooks 1/1.** Hooks land in `.claude/settings.json`,
the file Claude Code actually reads at user scope.

**The lockfile carries a real ownership manifest on this path** — this is what
discharges the local-path caveat:

```yaml
dependencies:
- repo_url: rb-chrismandich/apm-spike-522
  host: github.com
  resolved_commit: 34e73f256a1bd0f14f52424fc87519c1bf8b3e53
  deployed_files:
  - .claude/agents/spike-agent.md
  - .claude/skills/spike-alpha/SKILL.md
  - .claude/skills/spike-beta/SKILL.md
  deployed_file_hashes:
    .claude/skills/spike-alpha/SKILL.md: sha256:00e26b33f434e7d5…
```

Also measured on this path: **re-install byte-identical** ✅; **symlink fan-out
preserved** ✅ (`~/.cursor/skills -> ~/.claude/skills` survives
`--target claude,cursor`); **pinned `#v1.0.0`** resolves with
`resolved_ref: v1.0.0` and no unpinned warning ✅.

One inconsistency worth carrying forward rather than resolving here: every
`deployments[]` entry from a `-g` (user-scope) install is labelled
`scope: project` / `kind: project-relative`. The files land at user scope
correctly; only the lockfile's own label disagrees. Relevant to FR-014
(ownership enumeration) if that enumeration is ever driven off the lockfile's
`scope` field.

### Raw artifacts

Rig lives in the spike scratch dir (outside the repo, per the Phase 0 isolation
rule — T001–T006 modified nothing under `configs/`, `bootstrap*`, `.skillshare/`
or `tests/`):

- `sentinel.sh` — T003, with control case and churn exclusions (v3)
- `matrix.sh` — T005 cells (local source)
- `matrix-b.sh` — T005 cell (b), published package by name
- `pubrepo/` — the throwaway package as published, tagged `v1.0.0`
- `evidence/` — raw logs, hashes, before/after manifests, install transcripts,
  `T005b-apm.lock.yaml`

**Cleanup owed:** the private repo `RB-chrismandich/apm-spike-522` still exists.
It is a throwaway containing only the four spike primitives, kept so the cell
(b) result stays reproducible; delete it once Phase 1 no longer needs to re-run
the measurement.
