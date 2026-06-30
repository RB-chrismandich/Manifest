# Contract: Deploy-Time Integration

> Feature 368 — Deploy Reconciliation Review (Orphan Detection).
> Defines how the reconciliation review is wired into the bootstrap deploy flow:
> the exact call site, its report-only/fail-open contract, idempotency, the
> summary it prints, and its relationship to `verify_installation()`.
> Sources: `spec.md` (US2, FR-005/FR-006, SC-006), `research.md` Topic 5.

## Invariant (the one rule everything else serves)

**THE DEPLOY ENTRY POINT NEVER DELETES.** The deploy-time call is report-only
under every flag, option, and code path. It MUST NOT pass `--remove`, MUST NOT
move anything to the backup/trash, and MUST NOT create a backup directory.
Orphan removal happens exclusively through a separate, explicit, opt-in run of
`deploy_reconcile.sh --remove` (User Story 3 / FR-010), never as a side effect or
option of a routine deploy (FR-006).

## Function under contract

A new fail-open wrapper `reconcile_deploy_report()` is added to
`bootstrap/lib/deploy.sh`. It runs the deployed/source reconcile script in
**preview mode only** and prints its KEEP/REMOVE summary. It owns no removal
logic; it is a thin, guarded presentation layer over
`configs/claude/scripts/deploy_reconcile.sh`.

Command it issues (no destructive flags, ever):

```bash
deploy_reconcile.sh --project "$SCRIPT_DIR"   # preview; never --remove
```

## Exact call site

`bootstrap.sh` `main()`, immediately after the deploy block and before
`verify_installation`:

- `bootstrap.sh:260` — `deploy_configs`
- `bootstrap.sh:261` — `run_bootstrap_hook "after_deploy"`
- `bootstrap.sh:262` — `skillclaw_apply_state`
- **← insert `reconcile_deploy_report` here (after line 262)**, i.e. after
  `deploy_configs` and its `after_deploy` hook + skillclaw apply have settled,
  and before `verify_installation` at `bootstrap.sh:332`.

Guarded invocation (required form — see Fail-open):

```bash
reconcile_deploy_report || print_warning "reconcile review skipped (non-fatal)"
```

### Why `main()` and not inside `deploy_configs()`

`deploy_configs()` has **two** terminal paths:

- merge-mode early `return 0` at `bootstrap/lib/deploy.sh:117`
- full-mode end at `bootstrap/lib/deploy.sh:192`

A call placed inside `deploy_configs()` at the end would miss the merge-mode
early return (`deploy.sh:117`). Placing the single call in `main()` after
`deploy_configs` covers **both** deploy paths against the fully settled deployed
state with one invocation. (FR-005: the review must ALWAYS run as part of the
write/deploy step.)

This is also why the wiring is a direct `main()` call rather than an
`after_deploy`/`after_verify` module hook: those hooks are an optional extension
registry, and FR-005 requires the review to run on every deploy unconditionally.

## Report-only behavior (FR-005 / FR-006 / US2)

- Runs `deploy_reconcile.sh` in its **default preview mode** — no `--remove`,
  no confirmation prompt, no `/dev/tty` interaction.
- Prints the reconciliation **summary** to deploy output (counts of KEEP /
  REMOVE; the per-item list is available on demand via the skill). See "Summary"
  below.
- Makes **zero** changes to any managed root or to `~/.manifest`. A deploy-time
  run never creates a `reconcile-trash/<ts>/` directory (asserted by the
  deploy-time fail-open bats case, research Topic 6 case 15).
- US2 acceptance: orphans present → summary shown without interrupting a
  successful deploy; no orphans → clean result, no added noise, deploy not
  blocked; review completes → nothing deleted.

## Fail-open guarantee (P-V)

The deploy-time review is **advisory** and MUST NOT be able to fail the deploy.
`bootstrap.sh` runs under `set -e` (`bootstrap.sh:38`), so the call MUST be
guarded so a non-zero exit cannot abort bootstrap:

```bash
reconcile_deploy_report || print_warning "reconcile review skipped (non-fatal)"
```

Guarantees:

1. **Review error → warn, deploy continues.** Any failure inside
   `reconcile_deploy_report` (script missing, project root unresolvable [exit 2],
   transient error) is swallowed into a `print_warning`; bootstrap proceeds to
   `verify_installation` and `print_summary`.
2. **Orphans-found is NOT an error.** `deploy_reconcile.sh` returns exit 0 when
   orphans are merely found/reported (research Topic 5: "orphans-found NEVER
   yields nonzero"). Finding orphans never warns and never affects exit status.
3. **The report never contributes to `verify_errors`.** The reconcile call is
   independent of the `verify_installation || verify_errors=$?` accounting at
   `bootstrap.sh:331-332`. It does not increment `verify_errors`.
4. **Bootstrap still exits non-zero only on real deploy/verify failure.** The
   sole driver of `exit 1` remains `verify_errors > 0` (`bootstrap.sh:338-341`)
   and the hard pre-deploy failures inside `deploy_configs` (missing `rsync`
   `deploy.sh:53-63`, missing source dir `deploy.sh:65-68`). The advisory report
   neither suppresses those nor introduces new failure exits.

## Idempotency

- The deploy-time call is **pure-read**: preview mode performs no mutation, so
  running it 0, 1, or N times across repeated bootstraps yields the same
  deployed state (SC-002: 100% of preview runs leave the environment
  byte-for-byte unchanged).
- Detection is **stateless** (spec: current-deployed-vs-current-project). The
  report holds no history; each run recomputes from present state, so back-to-back
  deploys produce a consistent verdict for the same on-disk state.
- Because a deploy-time run never moves anything to trash, it can never create an
  artifact that a later run would re-report — idempotency holds across deploys
  without a self-exclusion step. (Trash self-exclusion matters only for the
  explicit `--remove` path, which is out of this contract.)

## Summary it prints

On a successful deploy the wrapper emits a one-line (plus optional per-class)
summary into deploy output, e.g.:

- Orphans present: `reconcile: N orphans (K keep, R remove) — run /deploy-reconcile to review`
- Clean: `reconcile: no orphans — deployed tree matches project`

The summary is the deploy-surfaced artifact required by FR-004 (summary counts)
and FR-005 (surfaced in deploy output). Full per-item KEEP/REMOVE detail is
obtained on demand via `/deploy-reconcile` (preview) — the deploy summary stays
terse to honor SC-006 ("adds no perceptible delay / no noise on a clean deploy").

## Relationship to `verify_installation()`

`verify_installation` and `reconcile_deploy_report` are **complementary and
independent**:

| Aspect | `verify_installation()` | `reconcile_deploy_report()` |
|--------|-------------------------|-----------------------------|
| Question | Is the **required** set of files **present**? (fixed required-files list, `deploy.sh:414-447`) | Are there **extra/orphaned** deployed units with **no project source**? |
| Direction | Missing-state (under-deploy) | Extra-state (drift / over-deploy) — the inverse |
| Effect on exit | Increments `verify_errors`; `verify_errors>0` → `exit 1` (`bootstrap.sh:331-341`) | None — advisory only, never touches `verify_errors` |
| Ordering | Runs at `bootstrap.sh:332` | Runs **before** it, after `deploy_configs` (after line 262) |

Ordering rationale: the reconcile report runs **before** `verify_installation`
so its summary appears alongside the deploy output, but it is explicitly excluded
from the `verify_errors` accounting that drives `exit 1`. This keeps the report
advisory (P-V) while bootstrap still exits non-zero on genuine verify failures.

## Performance budget (SC-006)

The deploy-time call must add no perceptible delay. The active-dependent /
dedup detection is a bounded reverse-symlink scan of the 4 secondary homes
(~20 realpath edges, research Topic 4), dwarfed by the deploy's own full-tree
`rsync -a` (`deploy.sh:144`) and `find -type f` over `~/.claude`
(`list_deployed_files`, `deploy.sh:199-206`).

## Cross-references

- Spec: FR-005, FR-006 (report-only entry point), US2, SC-002, SC-006.
- research.md Topic 5 (integration + entry points), Topic 4 (bounded detection).
- CLI contract for the underlying script: research.md Topic 5 / line 17–18.
