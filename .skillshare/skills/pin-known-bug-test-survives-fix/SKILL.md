---
name: pin-known-bug-test-survives-fix
description: Use when testing a known bug or placeholder you are NOT fixing now — make the assertion tolerate the post-fix output too, so the fix doesn't break the suite later. Anchor the real invariant separately.
---
# Pin Known-Buggy Behavior Without Breaking on the Fix

A naive `assert "<buggy value>"` becomes a tripwire that fails the day someone fixes the bug — quietly discouraging the fix. Write the pin so the eventual fix passes.

1. **Recognize the case.** You're adding coverage to document current behavior of code with a known defect (or deliberate placeholder) that is out of scope for this change.
2. **Assert an alternation, not a single value.** Accept current-buggy OR expected-after-fix: e.g. `assert_output --regexp "0 created, (2 updated, 0 unchanged|1 updated, 1 unchanged)"` — buggy form first, fixed form second.
3. **Comment the intent at the assertion.** Name the bug, the current value, and the value the fix should produce, so the alternation reads as deliberate, not sloppy.
4. **Anchor the real invariant elsewhere so the test keeps teeth.** Pin a checksum of the actual output (`shasum`) or a property that holds regardless of the buggy counter. The tolerant assertion documents the defect; the checksum proves the bytes are correct.
5. **Don't leak test-framework state.** If a helper uses bats `run` (which overwrites `$output`/`$status`), don't assert on `$output` *after* calling it — pass the expected value INTO the helper as a parameter instead.
6. **Track the underlying bug separately** (issue or follow-up task) so "pinned" doesn't decay into "forgotten."
7. **Tighten on fix.** When the bug is fixed, the alternation already passes — collapse it to the single expected value in that same PR.
