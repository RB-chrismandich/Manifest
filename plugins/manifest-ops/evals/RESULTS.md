# manifest-ops eval results

Full suite, 2026-09-27: manifest-ops 0.4.1, `runs: 3`, both arms, agent
`sonnet`, judge `opus`, run one skill prefix at a time (see README). Cost
$76.68; 3 of 504 runs hit their turn cap, none failed on infrastructure.

**Overall: with 0.78, without 0.53, Δ +0.25.**

| Skill | With | Without | Δ | Fire-case Δ | Neg with / without | Fired (fire runs) |
|-------|------|---------|---|-------------|--------------------|-------------------|
| cache-warm-oob (`cwo`) | 0.79 | 0.29 | +0.50 | +0.82 | 0.70 / 1.00 | 14/15 |
| version-pin (`vp`) | 0.97 | 0.59 | +0.38 | +0.56 | 0.93 / 1.00 | 15/15 |
| docker-compose-commandments (`dcc`) | 0.90 | 0.56 | +0.34 | +0.51 | 0.93 / 1.00 | 15/15 |
| process-diagnose-stall (`pds`) | 0.83 | 0.52 | +0.30 | +0.42 | 1.00 / 1.00 | 13/15 |
| docker-probe-internal (`dpi`) | 0.90 | 0.63 | +0.27 | +0.38 | 1.00 / 1.00 | 15/15 |
| ci-reproduce-failure (`crf`) | 0.53 | 0.31 | +0.22 | +0.28 | 0.87 / 0.80 | 15/15 |
| ci-diagnose-drift (`cdd`) | 0.83 | 0.62 | +0.21 | +0.30 | 1.00 / 1.00 | 15/15 |
| ci-setup (`cis`) | 0.98 | 0.78 | +0.21 | +0.31 | 0.94 / 1.00 | 15/15 |
| config-validate-native (`cvn`) | 0.63 | 0.44 | +0.19 | +0.27 | 1.00 / 1.00 | 15/15 |
| deploy-diagnose-drift (`ddd`) | 0.62 | 0.48 | +0.14 | +0.20 | 1.00 / 1.00 | 12/15 |
| config-debug-substitution (`cds`) | 0.67 | 0.58 | +0.10 | +0.13 | 1.00 / 1.00 | 14/15 |
| deploy-retire-component (`drc`) | 0.66 | 0.57 | +0.09 | +0.16 | 0.93 / 1.00 | 12/15 |

Spot-checked by hand: the largest jump (`cwo` fire cases) reflects the skill's
real method, not judge gaming. Negative dips other than `cwo-neg-01` are
single-run judge fails (1 of 3 runs).

## Plugin follow-ups (not fixed here; the suite tests the plugin as-is)

1. **cache-warm-oob over-triggers on real outages.** `cwo-neg-01` (manual curl
   also 503s): the skill fired in 2 of 3 runs and prescribed cache warming,
   which cannot succeed while the endpoint is down. Its description should
   exclude failing endpoints.
2. **cache-warm-oob writes `[]`/empty on non-200**, silently turning failed
   fetches into data that looks valid. Record failures visibly instead.
3. **cache-warm-oob vs process-diagnose-stall overlap.** On an I/O stall
   (`pds-02`) cache-warm-oob fires instead, and neither answer covers
   incremental caching for resume.
4. **ci-diagnose-drift / ci-reproduce-failure Step 0** stops when no CI config
   is on disk, so neither works from pasted configuration.
5. **ci-setup only fires when a real git repo exists** (it aborts otherwise);
   in a pasted-config conversation it never triggers.

## Environment limits

- `vp` cases cannot reach PyPI or a registry from the sandbox, so both arms can
  only take the honest `unresolved` path; Δ there measures honesty, not pinning.
- macOS agent sandboxes cannot run Apple `/usr/bin/git`; repo-dependent cases
  build their repo in `scaffold.sh` (requires `--scaffold`).
