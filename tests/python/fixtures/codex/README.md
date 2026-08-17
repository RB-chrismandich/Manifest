# Codex `exec --json` JSONL fixtures

Provenance for the `session_id_capture` (`jsonl_event`) coverage required by
T009 of `specs/675-multi-agent-delegation/tasks.md`.

| File | Provenance |
|------|------------|
| `exec_thread_started.jsonl` | **Captured live** from `codex exec --json --skip-git-repo-check --sandbox read-only` on `codex-cli 0.147.0` (2026-08-16), in a throwaway git repo. Absolute home paths were rewritten to `/home/user`; the event stream, ordering, and field names are byte-faithful otherwise. |
| `exec_no_thread_started.jsonl` | **Derived** from the capture above by removing the leading `thread.started` line — it stands in for an older codex CLI that does not emit that event. Not a live capture; every remaining line is. |

The registry (`plugins/manifest-delegate/config/backends.json`) declares
`{"method": "jsonl_event", "event": "thread.started", "field": "thread_id"}`.
The live capture confirms both the event name and the field name.

Consumed by `tests/python/test_delegate_session_capture.py`.
