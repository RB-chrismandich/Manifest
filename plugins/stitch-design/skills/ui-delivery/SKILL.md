---
name: ui-delivery
description: Own an approved, bounded UI build lifecycle with authorized changes and evidence.
---

# UI delivery lifecycle

1. **Preflight:** require `/stitch-design:ui-delivery`, `/stitch-design:ui-verification`, OMP-only `ui-builder` and `ui-reviewer`, custom tools `ui_apply_patch`, `ui_run_check`, and `ui_capture`, plus `references/task.schema.json` and `references/review.schema.json`. If any asset is unavailable, blocks work; there is no unrestricted fallback.
2. **Approval:** create and approve a task manifest with authorized paths, forbidden policy paths, approved fixed-argv checks, capture recipes, and the routed builder model. If Stitch is used, bind each mutation to a one-use input-hashed grant and readback tools.
3. **Build:** invoke `ui-builder` only for the approved manifest. Capture the exact candidate revision and hash before candidate review.
4. **Review:** hand the immutable candidate to `/stitch-design:ui-verification`; it validates the reviewer output against `references/review.schema.json`. The reviewer is read-only and returns evidence bound to that revision and hash.
5. **Repair:** authorized repairs may run at most twice. A third unresolved cycle is blocked, not retried.
6. **Terminal evidence:** accept only verified evidence. Failed checks yield `failed`; unavailable, skipped, or timed-out checks are `unverified`, never pass; authorization or recovery uncertainty yields `blocked`.
