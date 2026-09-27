---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. On resume, the answer says the checkpoint should NOT be trusted as-is because repository state changed since it was written.
2. It names what changed: HEAD moved (new commit) and the dirty-tree entries (modified app.py / untracked notes.txt) are no longer as recorded.
3. It says to reconcile those differences before acting, rather than blindly continuing from the checkpoint's next action.
4. The trace shows `session_continuity.py verify` (or the runtime's verify command) actually run with CURRENT git/operation snapshots, returning an untrusted result (e.g. `trusted: false`) that names the changed fields — the conclusion is backed by that output, not only by narrative.
