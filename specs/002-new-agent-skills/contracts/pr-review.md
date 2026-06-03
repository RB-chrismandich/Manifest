# Contract: `pr-review`

**Type**: Claude Code skill (`/pr-review`) + helper `configs/claude/scripts/pr_review.sh` (wraps `git_ops.sh` / `git_platform.sh`).

## Invocation

```
/pr-review [--platform github|gitlab] [--stale-days N] [--json]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--platform` | auto-detect | Override `git_platform.sh` detection. |
| `--stale-days` | config / 30 | Activity threshold for staleness signal. |
| `--json` | off | Emit machine-readable records. |

## Behavior contract

- **MUST** enumerate ALL open PRs via `git_ops.sh pr-list` and enrich each via `pr-view`/`pr-diff`/`pr-checks` (FR-012, R5).
- **MUST** produce per-PR: status, mergeability, staleness, superseded/merged flags, disposition + rationale (FR-013, data-model §3).
- **MUST** be analysis-only: zero mutations without an explicit action (FR-014). (Acting on a recommendation is a separate, confirmed step — out of scope for this skill's default run.)
- **MUST** report empty queue cleanly and unauthenticated/no-API distinctly (not as "clean") (FR-015).

## Output schema

```
Open PRs on <platform>: N
#<id>  <title>            <age>  <mergeable>/<checks>  → <disposition>
       rationale: <one line>
...
Recommended: close C, merge M, rebase R, keep K
```

`--json`: array of PR Assessment records (data-model §3).

## Acceptance mapping

US3 scenarios 1–4 → this contract. Tier 2 validation.
