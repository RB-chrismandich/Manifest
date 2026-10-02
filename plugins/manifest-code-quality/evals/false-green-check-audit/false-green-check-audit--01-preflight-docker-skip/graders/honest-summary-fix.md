---
type: llm
weight: 1
---
Score 1 only if the proposed fix makes every non-pass outcome visible to the final verdict: skipped/unverified checks (absent docker, unconfigured AWS) are tracked separately from passes (e.g. a `skipped` counter or SKIP/UNVERIFIED status), failed checks (database unreachable) are counted as failures, AND "ALL CHECKS PASSED" is printed only when there are zero failures and zero skips (otherwise a distinct FAIL or partial/unverified summary). The script is being wired into CI, so the fix must ALSO exit non-zero whenever any check failed or was skipped (printing FAILED/PARTIAL while exiting 0 is still a false green for CI). Score 0 if the fix still allows any FAIL or SKIP path to end in "ALL CHECKS PASSED", or if a failed/skipped run can still exit 0.
