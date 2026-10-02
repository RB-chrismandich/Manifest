---
type: llm
focus: trace
weight: 2
---
Pass only if ALL hold:
1. The trace shows the new test being RUN against the unfixed `check()` and FAILING (red) before the fix was applied.
2. The trace then shows the fix and the same test PASSING (green).
3. The test isolates state: sets `XDG_STATE_HOME` to a tmp dir (redirecting `HOME` too is fine but not required, since XDG takes precedence) so the absent-receipt case is controlled, rather than relying on the machine having no receipt.
4. The fixed `check()` maps ONLY a missing receipt (`FileNotFoundError`, or an explicit existence check) to "degraded" without breaking the present/installed case. A fix that keeps a blanket `except Exception` (or bare `except`) turning every read/permission/JSON-decode failure into "degraded" or "ok" FAILS this item.
5. The tests also prove malformed JSON (and/or another I/O failure such as an unreadable file) stays visible — it raises or yields a distinct error result — rather than being silently mapped to "degraded"/"ok".
