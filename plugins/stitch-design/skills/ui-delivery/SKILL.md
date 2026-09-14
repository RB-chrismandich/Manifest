---
name: ui-delivery
description: Own an approved, bounded UI build lifecycle with authorized changes and evidence.
---

# UI delivery lifecycle

1. **Preflight:** require `/stitch-design:ui-delivery`, `/stitch-design:ui-verification`, OMP-only `ui-builder` and `ui-reviewer`, custom tools `ui_apply_patch`, `ui_run_check`, and `ui_capture`, plus `references/task.schema.json` and `references/review.schema.json`. If any asset is unavailable, blocks work; there is no unrestricted fallback.
2. **Approval:** create and approve a task manifest with authorized paths, forbidden policy paths, approved fixed-argv checks, capture recipes, and `model_route: "@ui_code"`. If Stitch is used, bind each mutation to a one-use input-hashed grant and readback tools.
3. **Build:** invoke `ui-builder` only for the approved manifest and builder digest. Capture the exact candidate revision and hash; run only checks not referenced by capture recipes.
4. **Review transition:** the trusted coordinator validates current builder evidence, atomically changes the exact candidate to `reviewing` with `model_route: "@ui_review"`, recomputes the external digest, and starts a separate reviewer process. The old builder digest cannot capture.
5. **Review:** hand the immutable candidate to `/stitch-design:ui-verification`; it validates the reviewer output against `references/review.schema.json`. The reviewer captures evidence only through declared capture recipes and returns evidence bound to that revision, hash, reviewer route, and digest.
6. **Repair:** authorized repairs may run at most twice. A third unresolved cycle is blocked, not retried.
7. **Terminal evidence:** accept only verified evidence. Build checks bind to the equivalent `@ui_code` digest; captures bind to the current `@ui_review` digest. Failed checks yield `failed`; unavailable, skipped, timed-out, wrong-route, or wrong-digest checks are `unverified`, never pass; authorization or recovery uncertainty yields `blocked`.
8. **Repository transaction:** the protected repository-wide patch journal admits one patch transaction at a time; its presence blocks every task until explicit recovery completes, so patch application, candidate hashing, rollback, and task advancement cannot interleave.
