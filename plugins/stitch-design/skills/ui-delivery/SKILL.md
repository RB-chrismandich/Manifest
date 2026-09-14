---
name: ui-delivery
description: Own an approved, bounded UI build lifecycle with authorized changes and evidence.
---

# UI delivery lifecycle

1. **Preflight:** create a task manifest with authorized paths, forbidden policy paths, approved fixed-argv checks, capture recipes, and the routed builder model. Missing authorization blocks work.
2. **Approval:** obtain explicit design and task approval before a mutation. If Stitch is used, bind each mutation to a one-use input-hashed grant and readback tools.
3. **Build:** invoke the OMP-only `ui-builder` only for the approved manifest. Capture the exact candidate revision and hash before review.
4. **Review:** hand the immutable candidate to `/stitch-design:ui-verification`; the reviewer is read-only and returns evidence bound to that revision and hash.
5. **Repair:** authorized repairs may run at most twice. A third unresolved cycle is blocked, not retried.
6. **Terminal evidence:** accept only verified evidence. Failed checks yield `failed`; unavailable, skipped, or timed-out checks are `unverified`, never pass; authorization or recovery uncertainty yields `blocked`.
