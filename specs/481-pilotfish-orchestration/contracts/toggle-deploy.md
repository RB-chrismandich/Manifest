# Contract: Toggle + Deploy Behavior

**Surface**: `bootstrap.sh` flags, generated `services.yml`, and `gate_pilotfish_agents()` +
`check_pilotfish_collision()` in `bootstrap/lib/common.sh` (wired into `deploy.sh`). Consumer:
the Manifest operator running bootstrap.

## CLI + services.yml

- `--enable-pilotfish` / `--disable-pilotfish` (config.sh arg parser + `--help` usage).
- Defaults: `ENABLE_PILOTFISH=false`, `PILOTFISH_SET=false` (opt-in; skillclaw pattern).
- `write_services_config()` heredoc emits:
  ```yaml
  pilotfish:
    enabled: ${ENABLE_PILOTFISH:-false}
  ```
- The services.yml→FILE_* awk parser emits `FILE_PILOTFISH=true|false`.

## Deploy behavior (normative)

Both `configs/claude/agents/` and `configs/claude/references/pilotfish-delegation.md` are
**excluded** from the wholesale rsync (`--exclude '/agents' --exclude
'/references/pilotfish-delegation.md'`, like `/skills`); the gate is the sole deployer of both.
`check_pilotfish_collision "$home"` runs pre-rsync; `gate_pilotfish_agents "$home" "$src_agents"`
runs post-copy on the Claude deploy path:

| Phase / Toggle | Behavior |
|--------|----------|
| Pre-rsync guard (`ENABLE_PILOTFISH=true`) | If `~/.claude/agents/` lacks the `.pilotfish` marker AND already holds a file named as one of the **six** `PILOTFISH_AGENT_FILES` → **abort non-zero, name the file, touch nothing** (FR-008). A differently-named user agent is not a collision. No-op when disabled. |
| `FILE_PILOTFISH=true` (gate) | `mkdir` `~/.claude/agents/`, copy the six role files from `$src_agents` **and the reference** from `$(dirname "$src_agents")/references/pilotfish-delegation.md`, **write** the `.pilotfish` marker, inject the guide pointer. Idempotent (cp overwrites our own files; marker re-stamped; inject grep-guarded). |
| `FILE_PILOTFISH=false` (gate) | Manifest-scoped prune, and only when the marker is present: remove exactly the six deployed agents (via `PILOTFISH_AGENT_FILES`) + the `.pilotfish` marker + the reference + the injected guide pointer; `rmdir` the `agents/` dir only if empty. A coexisting user-authored agent — and a foreign unmarked `agents/` — survive untouched. |

Reconcile/orphan-prune: `deploy_reconcile` scans only `skills`/`config` units, so it does not
touch `~/.claude/agents/` at all — the deployed role files and any coexisting user agent are
never flagged or pruned by reconcile (R6). Disable pruning is done by the gate (above), scoped
to `PILOTFISH_AGENT_FILES` + marker.

## Invariants (testable — `tests/bats/deploy_pilotfish.bats`)

- **INV-1** (enable): after enable+deploy, the six agents + the reference exist at their targets.
- **INV-2** (disable clean): enable → snapshot `~/.claude` → disable → the tree is diff-identical
  to the pre-enable snapshot (SC-003) — nothing but pilotfish artifacts removed.
- **INV-3** (collision abort): with a pre-existing un-owned `~/.claude/agents/scout.md`, enable
  exits non-zero, the message names `scout.md`, and the pre-existing file is byte-identical
  afterward (FR-008). A differently-named `~/.claude/agents/my-agent.md` does **not** abort enable.
- **INV-4** (default off): a default bootstrap (no `--enable-pilotfish`) deploys **no** pilotfish
  artifacts and writes `pilotfish.enabled: false`. Because `agents/` is rsync-excluded and the
  disable prune runs only when the marker is present, a disabled run over a user-authored
  `~/.claude/agents/scout.md` leaves it byte-identical (no clobber).
- **INV-5** (idempotent): enable+deploy run twice yields the same tree, no error — the re-run
  re-copies + re-injects and reconverges (a no-op in effect, not a skip; Principle V).
- **INV-5b** (user-agent survival + re-enable): a user-authored `~/.claude/agents/my-agent.md`
  added after enable survives a subsequent disable (only the six + marker are removed, FR-006);
  and a *re-enable* afterward succeeds without a collision deadlock and redeploys the six.
- **INV-6** (budget): the **deployed** guide — committed source + the injected pointer line —
  stays under the `context_budget.bats` cap (7400), asserted by a source+pointer measurement, and
  `context_budget.bats` itself still passes on the (pointer-free) source (FR-009).
- **INV-7** (main-model untouched): deploy does not modify the `model` field of the deployed
  `settings.json`/`settings.local.json` and deploys no model-alias definition file (FR-016) —
  roles resolve via Claude Code's built-in `haiku`/`sonnet`/`opus` aliases.
